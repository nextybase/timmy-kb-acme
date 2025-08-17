# tests/test_drive_utils.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import hashlib
import io
import types
import pytest

import pipeline.drive_utils as DU
from pipeline.exceptions import ConfigError


# ------------------------------------------------------------
# Helpers finti per simulare googleapiclient senza rete
# ------------------------------------------------------------
class _FilesAPI:
    """Minimal fake per service.files() con metodi .create/.list/.delete/.get/.get_media"""

    def __init__(self, store: Dict[str, Dict[str, Any]]):
        # store: {id: {"name":..., "mimeType":..., "parents":[...], "content":bytes}}
        self.store = store
        self._next_id = 1

    # ---- create ----
    class _CreateReq:
        def __init__(self, files_api, body, media_body, fields, supportsAllDrives):
            self.files_api = files_api
            self.body = body
            self.media_body = media_body
            self.fields = fields
            self.supportsAllDrives = supportsAllDrives

        def execute(self):
            fid = f"id{self.files_api._next_id}"
            self.files_api._next_id += 1
            name = self.body.get("name")
            mime = self.body.get("mimeType") or "application/octet-stream"
            parents = self.body.get("parents", [])
            content = b""
            if self.media_body:
                # MediaFileUpload fake: accetta path o file-like; qui è già gestito dal test
                # Non abbiamo accesso diretto, quindi lasciamo vuoto.
                pass
            self.files_api.store[fid] = {
                "id": fid,
                "name": name,
                "mimeType": mime,
                "parents": parents,
                "content": content,
            }
            return {"id": fid}

    def create(self, body=None, media_body=None, fields=None, supportsAllDrives=None):
        return _FilesAPI._CreateReq(self, body or {}, media_body, fields, supportsAllDrives)

    # ---- list ----
    class _ListReq:
        def __init__(self, files_api, q, spaces, fields, pageToken, includeItemsFromAllDrives, supportsAllDrives):
            self.files_api = files_api
            self.q = q
            self.fields = fields

        def execute(self):
            # Filtra per parent e (eventuale) mimeType in query
            # Query tipica: "'<PARENT>' in parents and trashed = false and mimeType = '<MIME>'"
            q = self.q or ""
            # Estraggo parent
            parent_id = None
            if "' in parents" in q:
                # semplice parsing
                start = q.find("'") + 1
                end = q.find("'", start)
                parent_id = q[start:end]

            mime_filter = None
            if "mimeType =" in q:
                mstart = q.find("mimeType =") + len("mimeType =")
                part = q[mstart:].strip()
                if part.startswith("'"):
                    mend = part.find("'", 1)
                    mime_filter = part[1:mend]

            out: List[Dict[str, Any]] = []
            for obj in self.files_api.store.values():
                if parent_id and parent_id not in obj.get("parents", []):
                    continue
                if mime_filter and obj.get("mimeType") != mime_filter:
                    continue
                if obj.get("trashed"):
                    continue
                out.append({
                    "id": obj["id"],
                    "name": obj["name"],
                    "mimeType": obj["mimeType"],
                    "md5Checksum": hashlib.md5(obj.get("content", b"")).hexdigest() if obj.get("content") else None,
                    "size": str(len(obj.get("content", b""))) if obj.get("content") else None,
                })
            return {"files": out, "nextPageToken": None}

    def list(self, q=None, spaces=None, fields=None, pageToken=None, includeItemsFromAllDrives=None, supportsAllDrives=None):
        return _FilesAPI._ListReq(self, q, spaces, fields, pageToken, includeItemsFromAllDrives, supportsAllDrives)

    # ---- delete ----
    class _DeleteReq:
        def __init__(self, files_api, fileId, supportsAllDrives):
            self.files_api = files_api
            self.fileId = fileId

        def execute(self):
            self.files_api.store.pop(self.fileId, None)
            return {}

    def delete(self, fileId=None, supportsAllDrives=None):
        return _FilesAPI._DeleteReq(self, fileId, supportsAllDrives)

    # ---- get (metadata) ----
    class _GetReq:
        def __init__(self, files_api, fileId, fields, supportsAllDrives):
            self.files_api = files_api
            self.fileId = fileId

        def execute(self):
            obj = self.files_api.store[self.fileId]
            meta = {
                "name": obj["name"],
                "size": str(len(obj.get("content", b""))) if obj.get("content") else None,
                "md5Checksum": hashlib.md5(obj.get("content", b"")).hexdigest() if obj.get("content") else None,
            }
            return meta

    def get(self, fileId=None, fields=None, supportsAllDrives=None):
        return _FilesAPI._GetReq(self, fileId, fields, supportsAllDrives)

    # ---- get_media (contenuto) ----
    class _GetMediaReq:
        def __init__(self, files_api, fileId, supportsAllDrives):
            self.files_api = files_api
            self.fileId = fileId

        def read(self, *a, **k):
            return self.files_api.store[self.fileId].get("content", b"")

    def get_media(self, fileId=None, supportsAllDrives=None):
        return _FilesAPI._GetMediaReq(self, fileId, supportsAllDrives)


class _Service:
    def __init__(self, store):
        self._files = _FilesAPI(store)

    def files(self):
        return self._files


class _Downloader:
    """Stub di MediaIoBaseDownload: scrive tutto in un colpo su fh e termina."""
    def __init__(self, fh, request):
        self.fh = fh
        self.request = request
        self._done = False

    def next_chunk(self):
        if self._done:
            return (None, True)
        data = self.request.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.fh.write(data or b"")
        # finto status con .progress()
        status = types.SimpleNamespace(progress=lambda: 1.0)
        self._done = True
        return (status, True)


# ------------------------------------------------------------
# Test
# ------------------------------------------------------------
def test_create_drive_structure_from_yaml_adds_aliases(tmp_path, monkeypatch):
    """
    Verifica:
      - accetta YAML in formato moderno e legacy
      - crea cartelle (nessun 409) e RITORNA alias RAW/YAML solo nel dict finale
    """
    # YAML "moderno": RAW e YAML
    y = tmp_path / "tree.yaml"
    y.write_text("""
RAW:
  Contratti: {}
  Report: {}
YAML:
  Schemi: {}
""", encoding="utf-8")

    # Fake Drive vuoto: create/list funzionano localmente
    store: Dict[str, Dict[str, Any]] = {
        "root": {"id": "root", "name": "root", "mimeType": DU.MIME_FOLDER, "parents": []}
    }
    service = _Service(store)

    # Patch: evita chiamate reali a Google, ma lascia la nostra implementazione interna
    monkeypatch.setattr(DU, "build", lambda *a, **k: None, raising=False)  # non usato qui
    # list_drive_files / create_drive_folder usano service.files(), quindi OK

    created = DU.create_drive_structure_from_yaml(service, y, "root")
    # Devono comparire almeno le chiavi 'raw','yaml' create e gli alias RAW/YAML
    assert "Contratti" in created or "contratti" in (k.lower() for k in created.keys())
    assert "RAW" in created or "raw" in created
    assert "YAML" in created or "yaml" in created


def test_create_local_base_structure_creates_only_RAW_categories(tmp_path):
    """
    Verifica che localmente vengano create solo le categorie sotto RAW/raw.
    """
    # YAML con RAW e altre sezioni
    y = tmp_path / "tree.yaml"
    y.write_text("""
RAW:
  Contratti: {}
  Report: {}
ALTRO:
  Ignorami: {}
""", encoding="utf-8")

    class _Ctx:
        output_dir: Path = tmp_path
        # i nomi di default del modulo sono output/raw, output/book, output/config
        raw_dir: Path = tmp_path / "raw"
        md_dir: Path = tmp_path / "book"
        config_dir: Path = tmp_path / "config"
        slug = "dummy"

    DU.create_local_base_structure(_Ctx, y)

    # Struttura fissa
    assert (_Ctx.raw_dir).exists()
    assert (_Ctx.md_dir).exists()
    assert (_Ctx.config_dir).exists()

    # Solo categorie da RAW
    assert (tmp_path / "raw" / "Contratti").exists()
    assert (tmp_path / "raw" / "Report").exists()
    assert not (tmp_path / "raw" / "Ignorami").exists()


def test_download_pdfs_recursive_idempotent_skip(tmp_path, monkeypatch):
    """
    Verifica download ricorsivo BFS con:
      - cartelle annidate
      - confronto size/md5
      - secondo giro = skip (idempotenza)
    """
    # Costruiamo una gerarchia Drive:
    # root/
    #   Cat1/ (folder)
    #       doc1.pdf (content=b'PDF1')
    #       Sub/ (folder)
    #           doc2.pdf (content=b'XY')
    store: Dict[str, Dict[str, Any]] = {
        "root": {"id": "root", "name": "root", "mimeType": DU.MIME_FOLDER, "parents": []},
        "f1":   {"id": "f1",   "name": "Cat1", "mimeType": DU.MIME_FOLDER, "parents": ["root"]},
        "p1":   {"id": "p1",   "name": "doc1.pdf", "mimeType": DU.MIME_PDF, "parents": ["f1"], "content": b"PDF1"},
        "f2":   {"id": "f2",   "name": "Sub", "mimeType": DU.MIME_FOLDER, "parents": ["f1"]},
        "p2":   {"id": "p2",   "name": "doc2.pdf", "mimeType": DU.MIME_PDF, "parents": ["f2"], "content": b"XY"},
    }
    service = _Service(store)

    # Monkeypatch della classe downloader per evitare dipendenze reali
    monkeypatch.setattr(DU, "MediaIoBaseDownload", _Downloader, raising=True)

    # Esegui download nella cartella locale
    local = tmp_path / "raw"
    downloaded, skipped = DU.download_drive_pdfs_to_local(
        service,
        remote_root_folder_id="root",
        local_root_dir=local,
        progress=True,
    )
    assert downloaded == 2 and skipped == 0
    assert (local / "Cat1" / "doc1.pdf").exists()
    assert (local / "Cat1" / "Sub" / "doc2.pdf").exists()

    # Secondo giro: deve saltare entrambi (size uguale)
    downloaded2, skipped2 = DU.download_drive_pdfs_to_local(
        service,
        remote_root_folder_id="root",
        local_root_dir=local,
        progress=False,
    )
    assert downloaded2 == 0 and skipped2 >= 2


def test_create_drive_structure_from_yaml_legacy_format(tmp_path):
    """
    Accetta anche il formato legacy con 'root_folders': [{name, subfolders:[...]}]
    """
    y = tmp_path / "legacy.yaml"
    y.write_text("""
root_folders:
  - name: raw
    subfolders:
      - name: Contratti
      - name: Report
  - name: yaml
""", encoding="utf-8")

    store: Dict[str, Dict[str, Any]] = {
        "root": {"id": "root", "name": "root", "mimeType": DU.MIME_FOLDER, "parents": []}
    }
    service = _Service(store)

    created = DU.create_drive_structure_from_yaml(service, y, "root")
    # deve contenere i nomi principali e gli alias
    for k in ("raw", "yaml", "RAW", "YAML"):
        assert any(key.lower() == k.lower() for key in created.keys())


def test_create_local_base_structure_raises_if_yaml_missing(tmp_path):
    class _Ctx:
        output_dir: Path = tmp_path
        raw_dir: Path = tmp_path / "raw"
        md_dir: Path = tmp_path / "book"
        config_dir: Path = tmp_path / "config"
        slug = "dummy"

    with pytest.raises(ConfigError):
        DU.create_local_base_structure(_Ctx, tmp_path / "missing.yaml")
