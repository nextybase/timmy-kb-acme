# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/download.py
"""Download da Google Drive → sandbox locale (RAW) con commit **atomico**.

Cosa fa
-------
- Esplora ricorsivamente una cartella di Drive (`remote_root_folder_id`) e
  scarica **solo i PDF** mantenendo la stessa gerarchia locale sotto
  `local_root_dir` (tipicamente: `output/timmy-kb-<slug>/raw`).
- Ogni file è scritto in modo **atomico**: stream su file temporaneo nello
  stesso folder, `flush` + `fsync`, quindi `os.replace()` sul path finale.
- **Path-safety STRONG**: prima di creare directory o scrivere file, verifica che
  il path di destinazione sia *dentro* la sandbox del cliente (`ensure_within`).
- **Idempotenza**: se il file esiste e la dimensione corrisponde, salta la copia.
- **Logging strutturato**: usa `get_structured_logger`; mai `print()`.

API pubblica
------------
download_drive_pdfs_to_local(
    service,
    remote_root_folder_id: str,
    local_root_dir: Path,
    *,
    progress: bool = False,
    context=None,
    redact_logs: bool = False,
) -> int
    Ritorna il numero di PDF scaricati (nuovi/aggiornati).

Dipendenze
----------
- google-api-python-client (MediaIoBaseDownload)
- pipeline.logging_utils, pipeline.path_utils, pipeline.exceptions
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from googleapiclient.http import MediaIoBaseDownload

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.logging_utils import get_structured_logger, redact_secrets, tail_path
from pipeline.path_utils import ensure_within, sanitize_filename

# MIME costanti basilari (allineate alla facciata)
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_PDF = "application/pdf"

# Chunk di download (8 MiB bilanciato per throughput/ram)
_DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024


def _q_parent(parent_id: str) -> str:
    # Query Drive V3: figli non cestinati
    return f"'{parent_id}' in parents and trashed = false"


def _list_children(service: Any, parent_id: str, *, fields: str) -> List[Dict[str, Any]]:
    """Lista i children di un folder (una pagina alla volta)."""
    items: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while True:
        req = service.files().list(
            q=_q_parent(parent_id),
            fields=f"nextPageToken, files({fields})",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        resp = req.execute()
        items.extend(resp.get("files", []) or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def _walk_drive_tree(service: Any, root_id: str) -> Iterable[Tuple[List[str], Dict[str, Any]]]:
    """
    DFS: restituisce tuple (path_parts, item) per ogni file/cartella sotto root.
    path_parts = lista di nomi cartella dal root ai figli (sanificati).
    """
    stack: List[Tuple[str, List[str]]] = [(root_id, [])]
    while stack:
        folder_id, parts = stack.pop()
        children = _list_children(
            service,
            folder_id,
            fields="id, name, mimeType, size",
        )
        for it in children:
            name = sanitize_filename(it.get("name") or "")
            if not name:
                # Fallback generico, utile in casi estremi di nomi vuoti
                name = f"item-{it.get('id','unknown')[:8]}"
            mime = it.get("mimeType")
            if mime == MIME_FOLDER:
                stack.append((it["id"], parts + [name]))
                yield (parts, it)  # opzionale: superficie per chi vuole “vedere” anche le cartelle
            else:
                yield (parts, it)


def _ensure_dest(base_dir: Path, local_root_dir: Path, rel_parts: List[str], filename: str) -> Path:
    """Prepara il path di destinazione garantendo path-safety STRONG e creazione directory."""
    # Cartella destinazione = local_root_dir / rel_parts...
    dest_dir = (local_root_dir.joinpath(*rel_parts)).resolve()
    ensure_within(base_dir, dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = (dest_dir / filename).resolve()
    ensure_within(base_dir, dest_path)
    return dest_path


def _download_one_pdf_atomic(
    service: Any,
    file_id: str,
    dest_path: Path,
    *,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    logger: Any,
    progress: bool = False,
) -> None:
    """Scarica un singolo PDF in maniera **atomica**:

    - scrive su file temporaneo nello stesso folder
    - flush + fsync
    - os.replace() sul path finale
    """
    # Request media
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)

    # Temp nello stesso folder (così os.replace è atomico sullo stesso FS)
    dest_dir = dest_path.parent
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, dir=str(dest_dir)) as tmp:
        tmp_name = tmp.name
        downloader = MediaIoBaseDownload(tmp, request, chunksize=int(chunk_size))

        last_pct = -1
        while True:
            status, done = downloader.next_chunk()
            if status and progress:
                pct = int((status.progress() or 0.0) * 100)
                # Logga a soglie intere (evita flood)
                if pct != last_pct and pct % 10 == 0:
                    logger.info(
                        "download.progress",
                        extra={"file_path": str(dest_path), "progress_pct": pct},
                    )
                    last_pct = pct
            if done:
                break

        # Commit atomico
        tmp.flush()
        os.fsync(tmp.fileno())
    os.replace(tmp_name, dest_path)


def download_drive_pdfs_to_local(
    service: Any,
    remote_root_folder_id: str,
    local_root_dir: Path,
    *,
    progress: bool = False,
    context: Any | None = None,
    redact_logs: bool = False,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> int:
    """Scarica ricorsivamente **solo i PDF** da una cartella Drive verso `local_root_dir`.

    Args:
        service: client Drive v3 già autenticato (googleapiclient).
        remote_root_folder_id: ID della cartella radice su Drive.
        local_root_dir: cartella locale “raw/” dentro la sandbox cliente.
        progress: se True, logga avanzamento al 10/20/.../100%.
        context: ClientContext opzionale per log arricchiti (slug, base_dir, redact).
        redact_logs: se True, redige ID sensibili nei log.
        chunk_size: dimensione chunk per MediaIoBaseDownload (byte).

    Returns:
        Numero di PDF scaricati (nuovi/aggiornati).
    """
    logger = get_structured_logger("pipeline.drive.download", context=context)
    local_root_dir = Path(local_root_dir).resolve()

    # Base sandbox: preferisci context.base_dir; fallback al genitore di local_root_dir
    base_dir = Path(getattr(context, "base_dir", local_root_dir.parent)).resolve()

    # STRONG: local_root_dir deve essere *dentro* base_dir
    try:
        ensure_within(base_dir, local_root_dir)
        local_root_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ConfigError(
            f"Path di destinazione non sicuro: {local_root_dir} ({e})",
            file_path=str(local_root_dir),
        ) from e

    rid_masked = redact_secrets(remote_root_folder_id) if redact_logs else remote_root_folder_id
    logger.info(
        "drive.download.start",
        extra={
            "remote_root": rid_masked,
            "local_root": str(local_root_dir),
            "local_tail": tail_path(local_root_dir),
        },
    )

    downloaded = 0
    errors: List[Tuple[str, str]] = []

    # DFS sul tree Drive
    for rel_parts, item in _walk_drive_tree(service, remote_root_folder_id):
        mime = item.get("mimeType")
        if mime == MIME_FOLDER:
            # opzionale: crea i folder locali in anticipo (non strettamente necessario)
            try:
                _ = _ensure_dest(base_dir, local_root_dir, rel_parts, "__keep__").parent
            except Exception as e:
                logger.warning("folder.ensure.fail", extra={"parts": rel_parts, "error": str(e)})
            continue

        if mime != MIME_PDF:
            continue  # scarichiamo solo PDF

        file_id = item["id"]
        name = sanitize_filename(item.get("name") or f"{file_id}.pdf")
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"

        # Prepara destinazione con guard-rail STRONG
        try:
            dest_path = _ensure_dest(base_dir, local_root_dir, rel_parts, name)
        except Exception as e:
            logger.warning("dest.ensure.fail", extra={"file": name, "error": str(e)})
            continue

        # Idempotenza semplice: skip se size invariata
        remote_size = int(item.get("size") or 0)
        if dest_path.exists() and remote_size > 0:
            try:
                if dest_path.stat().st_size == remote_size:
                    logger.debug(
                        "download.skip.same_size",
                        extra={"file_path": str(dest_path), "size": remote_size},
                    )
                    continue
            except OSError:
                pass

        # Download atomico
        try:
            _download_one_pdf_atomic(
                service,
                file_id=file_id,
                dest_path=dest_path,
                chunk_size=chunk_size,
                logger=logger,
                progress=progress,
            )
            downloaded += 1
            logger.info("download.ok", extra={"file_path": str(dest_path), "size": remote_size})
        except Exception as e:
            fid = redact_secrets(file_id) if redact_logs else file_id
            errors.append((fid, str(e)))
            logger.warning(
                "download.fail",
                extra={"file_id": fid, "error": str(e), "file_path": str(dest_path)},
            )

    if errors:
        # Non interrompiamo il flusso, ma segnaliamo in maniera aggregata
        msg = f"Download completato con errori: {len(errors)} elementi falliti."
        raise PipelineError(msg, slug=getattr(context, "slug", None))

    logger.info("drive.download.end", extra={"downloaded": downloaded})
    return downloaded
