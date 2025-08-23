# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/upload.py
"""
Operazioni di creazione/aggiornamento su Google Drive e struttura locale.

Superficie pubblica (richiamata via `pipeline.drive_utils`):
- create_drive_folder(service, name, parent_id=None, *, redact_logs=False) -> str
- create_drive_structure_from_yaml(service, yaml_path, client_folder_id, *, redact_logs=False) -> dict[str, str]
- upload_config_to_drive_folder(service, context, parent_id, *, redact_logs=False) -> str
- delete_drive_file(service, file_id) -> None
- create_local_base_structure(context, yaml_path) -> None

Obiettivi:
- Mantenere firme/contratti esistenti (UX invariata).
- Idempotenza su creazione cartelle e upload config.
- Compatibilità Shared Drives (supportsAllDrives=True).
- Logging strutturato con redazione opzionale.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, List, Union
from os import PathLike

import yaml  # type: ignore
from googleapiclient.errors import HttpError  # type: ignore

from ..exceptions import ConfigError, DriveUploadError
from ..logging_utils import get_structured_logger
from ..path_utils import sanitize_filename
from ..constants import OUTPUT_DIR_NAME
from .client import _retry

logger = get_structured_logger("pipeline.drive.upload")

_FOLDER_MIME = "application/vnd.google-apps.folder"


# ------------------------------- Utilità locali -----------------------------------


def _maybe_redact(text: str, redact: bool) -> str:
    """Oscura parzialmente il testo nei log quando `redact` è attivo."""
    if not redact or not text:
        return text
    t = str(text)
    if len(t) <= 7:
        return "***"
    return f"{t[:3]}***{t[-3:]}"


def _ensure_dir(path: Path) -> None:
    """Crea una directory se non esiste (idempotente)."""
    path.mkdir(parents=True, exist_ok=True)


def _list_existing_folder_by_name(service: Any, parent_id: Optional[str], name: str) -> Optional[str]:
    """
    Ritorna l'ID di una cartella già esistente con `name` sotto `parent_id`, se presente.
    Se `parent_id` è None, cerca a livello "root" dell'utente/service account.
    """
    base = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q = f"{base} and '{parent_id}' in parents and name = '{name}'"
    else:
        q = f"{base} and name = '{name}'"

    def _call():
        req = (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="files(id, name)",
                pageSize=10,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
        )
        return req.execute()

    resp = _retry(_call, op_name="files.list.folder_by_name")
    files = resp.get("files", [])
    if not files:
        return None
    return files[0]["id"]


def _create_folder(service: Any, name: str, parent_id: Optional[str]) -> str:
    """
    Crea una cartella su Drive e ritorna l'ID.
    Non esegue lookup: la responsabilità di idempotenza è nel chiamante.
    """
    body = {"name": name, "mimeType": _FOLDER_MIME}
    if parent_id:
        body["parents"] = [parent_id]

    def _call():
        return (
            service.files()
            .create(body=body, fields="id", supportsAllDrives=True)
            .execute()
        )

    resp = _retry(_call, op_name="files.create.folder")
    return resp["id"]


def _delete_file_hard(service: Any, file_id: str) -> None:
    """Elimina un file su Drive; ignora il 404 (già non presente)."""
    def _call():
        return service.files().delete(fileId=file_id, supportsAllDrives=True).execute()

    try:
        _retry(_call, op_name="files.delete")
    except HttpError as e:  # type: ignore[reportGeneralTypeIssues]
        try:
            status = int(e.resp.status)  # type: ignore[attr-defined]
        except Exception:
            status = None
        if status == 404:
            return
        raise


# ------------------------------- Normalizzazione YAML -----------------------------


def _normalize_yaml_structure(data: Any) -> Dict[str, Any]:
    """
    Normalizza la struttura YAML della gerarchia remota in un **mapping annidato**.

    Formati supportati (compat col monolite):
    1) **Moderno**: dict con chiavi qualsiasi (es. RAW/YAML o categorie libere)
    2) **Legacy**: dict con chiave `root_folders` che è una **lista** di oggetti:
       - Ogni oggetto: { name: "<cartella>", subfolders: [ ... ] } ricorsivo
    3) **Fallback permissivo**: se è un dict ma non contiene né RAW/YAML né root_folders,
       viene usato così com'è (nessun errore).

    Ritorna un dict annidato pronto per `_create_remote_tree_from_mapping`.
    """
    if isinstance(data, dict):
        # Legacy con root_folders lista
        if isinstance(data.get("root_folders"), list):
            def to_map(items: List[dict]) -> Dict[str, Any]:
                out: Dict[str, Any] = {}
                for it in items:
                    name = it.get("name")
                    subs = it.get("subfolders") or []
                    if not name:
                        continue
                    out[str(name)] = to_map(subs) if subs else {}
                return out
            return to_map(data["root_folders"])
        # Moderno/generico: accetta il dict così com'è
        return data

    raise ConfigError("Struttura YAML non valida: atteso un mapping o un root_folders:list.")


# ------------------------------- API: Cartelle/Albero -----------------------------


def create_drive_folder(
    service: Any,
    name: str,
    parent_id: Optional[str] = None,
    *,
    redact_logs: bool = False,
) -> str:
    """
    Crea (idempotente) una cartella `name` sotto `parent_id` e ne ritorna l'ID.

    Regole:
    - Se una cartella con lo stesso nome esiste già sotto `parent_id`, riusa l'ID esistente.
    - Se non esiste, la crea.
    """
    if not name:
        raise DriveUploadError("Nome cartella mancante.")

    existing = _list_existing_folder_by_name(service, parent_id, name)
    if existing:
        logger.info(
            "drive.upload.folder.reuse",
            extra={
                "parent": _maybe_redact(parent_id or "root", redact_logs),
                "folder_name": name,          # ⚠️ niente chiave 'name'
                "folder_id": existing,        # uniforme
            },
        )
        return existing

    try:
        new_id = _create_folder(service, name, parent_id)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "drive.upload.folder.create_error",
            extra={
                "parent": _maybe_redact(parent_id or "root", redact_logs),
                "folder_name": name,          # ⚠️ niente chiave 'name'
                "message": str(e)[:300],
            },
        )
        raise DriveUploadError(f"Creazione cartella fallita: {name}") from e

    logger.info(
        "drive.upload.folder.created",
        extra={
            "parent": _maybe_redact(parent_id or "root", redact_logs),
            "folder_name": name,              # ⚠️ niente chiave 'name'
            "folder_id": new_id,
        },
    )
    return new_id


def _create_remote_tree_from_mapping(
    service: Any,
    parent_id: str,
    mapping: Dict[str, Any],
    *,
    redact_logs: bool = False,
    result: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Crea ricorsivamente un albero di cartelle da una mappatura {nome: sottoalbero}.
    Ritorna/aggiorna un dizionario `result` con {nome_livello: id} per i nodi creati.
    """
    if result is None:
        result = {}

    for raw_name, subtree in (mapping or {}).items():
        name = sanitize_filename(str(raw_name))
        folder_id = create_drive_folder(service, name, parent_id, redact_logs=redact_logs)
        result[name] = folder_id

        if isinstance(subtree, dict):
            _create_remote_tree_from_mapping(service, folder_id, subtree, redact_logs=redact_logs, result=result)
        elif isinstance(subtree, (list, tuple)):
            for leaf in subtree:
                leaf_name = sanitize_filename(str(leaf))
                leaf_id = create_drive_folder(service, leaf_name, folder_id, redact_logs=redact_logs)
                result[leaf_name] = leaf_id
        else:
            pass

    return result


def create_drive_structure_from_yaml(
    service: Any,
    yaml_path: Union[str, PathLike[str]],
    client_folder_id: str,
    *,
    redact_logs: bool = False,
) -> Dict[str, str]:
    """
    Crea la struttura di cartelle remota a partire da un file YAML.

    Comportamento:
    - NON forza la creazione di `RAW`/`YAML`: usa la mappatura risultante (moderna o legacy).
    - Ritorna una mappa nome→ID; se compaiono `raw`/`RAW` o `yaml`/`YAML`,
      aggiunge gli alias corrispondenti **solo nel risultato** (nessuna cartella extra).
    """
    if not os.path.isfile(str(yaml_path)):
        raise ConfigError(f"File YAML di struttura non trovato: {yaml_path}")

    try:
        with open(str(yaml_path), "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"Impossibile leggere/parsing YAML: {e}") from e

    mapping = _normalize_yaml_structure(data)

    result: Dict[str, str] = {}
    _create_remote_tree_from_mapping(service, client_folder_id, mapping, redact_logs=redact_logs, result=result)

    # Alias SOLO nel risultato (compat CLI/orchestratori)
    if "raw" in result and "RAW" not in result:
        result["RAW"] = result["raw"]
    if "RAW" in result and "raw" not in result:
        result["raw"] = result["RAW"]
    if "yaml" in result and "YAML" not in result:
        result["YAML"] = result["yaml"]
    if "YAML" in result and "yaml" not in result:
        result["yaml"] = result["YAML"]

    logger.info(
        "drive.upload.tree.created",
        extra={"client_root": _maybe_redact(client_folder_id, redact_logs), "keys": list(result.keys())[:10]},
    )
    return result


# ------------------------------- Upload config ------------------------------------


def _resolve_local_config_path(context: Any) -> Path:
    """
    Risolve il percorso locale del file `config.yaml` secondo convenzioni note.

    Ordine tentativi (conservativo):
    1) attributi diretti sul contesto
    2) <config_dir>/config.yaml
    3) <client_dir>/config/config.yaml
    """
    candidates = []
    for attr in (
        "config_file",
        "config_path",
        "CONFIG_FILE",
        "CONFIG_PATH",
        "config_yaml_path",
        "client_config_file",
    ):
        if hasattr(context, attr):
            cand = getattr(context, attr)
            if isinstance(cand, (str, os.PathLike)) and str(cand):
                candidates.append(str(cand))

    if hasattr(context, "config_dir"):
        dir_path = getattr(context, "config_dir")
        if dir_path:
            candidates.append(os.path.join(str(dir_path), "config.yaml"))

    if hasattr(context, "client_dir"):
        base = getattr(context, "client_dir")
        if base:
            candidates.append(os.path.join(str(base), "config", "config.yaml"))

    for cand in candidates:
        p = Path(os.path.expanduser(str(cand))).resolve()
        if p.is_file():
            return p

    raise ConfigError("Impossibile individuare il file locale config.yaml nel contesto fornito.")


def _find_existing_child_file_by_name(service: Any, parent_id: str, name: str) -> Optional[str]:
    """Ritorna l'ID di un file figlio con `name` sotto `parent_id`, altrimenti None."""
    q = f"name = '{name}' and '{parent_id}' in parents and trashed = false"

    def _call():
        return (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="files(id, name)",
                pageSize=10,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )

    resp = _retry(_call, op_name="files.list.config_by_name")
    files = resp.get("files", [])
    if not files:
        return None
    return files[0]["id"]


def upload_config_to_drive_folder(
    service: Any,
    context: Any,
    parent_id: str,
    *,
    redact_logs: bool = False,
) -> str:
    """
    Carica il file `config.yaml` nella cartella cliente (sostituzione sicura se esiste).
    """
    if not parent_id:
        raise DriveUploadError("Parent ID mancante per upload config.")

    local_config = _resolve_local_config_path(context)
    if not local_config.is_file():
        raise DriveUploadError(f"File locale non trovato: {local_config}")

    existing_id = _find_existing_child_file_by_name(service, parent_id, "config.yaml")
    if existing_id:
        logger.info(
            "drive.upload.config.replace",
            extra={"parent": _maybe_redact(parent_id, redact_logs), "old_id": existing_id},
        )
        _delete_file_hard(service, existing_id)

    # Lazy import: disponibile solo se effettivamente carichiamo il file
    try:
        from googleapiclient.http import MediaFileUpload  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise DriveUploadError(
            "Dipendenza mancante per upload su Drive: google-api-python-client. "
            "Installa la libreria o usa --dry-run."
        ) from e

    media = MediaFileUpload(str(local_config), mimetype="application/octet-stream", resumable=False)
    body = {"name": "config.yaml", "parents": [parent_id]}

    def _call():
        return (
            service.files()
            .create(body=body, media_body=media, fields="id", supportsAllDrives=True)
            .execute()
        )

    try:
        resp = _retry(_call, op_name="files.create.config")
    except Exception as e:  # noqa: BLE001
        logger.error(
            "drive.upload.config.error",
            extra={
                "parent": _maybe_redact(parent_id, redact_logs),
                "local": str(local_config),
                "message": str(e)[:300],
            },
        )
        raise DriveUploadError(f"Upload config.yaml fallito: {e}") from e

    file_id = resp["id"]
    logger.info(
        "drive.upload.config.done",
        extra={"parent": _maybe_redact(parent_id, redact_logs), "file_id": file_id, "local": str(local_config)},
    )
    return file_id


# ------------------------------- Struttura LOCALE (permissiva) --------------------


def _read_yaml_structure(yaml_path: Union[str, PathLike[str]]) -> Dict[str, Any]:
    """Carica il file YAML e ritorna la struttura normalizzata (vedi _normalize_yaml_structure)."""
    if not os.path.isfile(str(yaml_path)):
        raise ConfigError(f"File YAML di struttura non trovato: {yaml_path}")
    try:
        with open(str(yaml_path), "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"Impossibile leggere/parsing YAML: {e}") from e
    return _normalize_yaml_structure(data)


def create_local_base_structure(context: Any, yaml_path: Union[str, PathLike[str]]) -> None:
    """
    Crea la struttura LOCALE di base in modo **permissivo**.

    Comportamento:
    - Determina una base directory:
        * `context.output_dir` oppure `context.base_dir`
        * altrimenti fallback: `output/timmy-kb-<slug>`
    - Garantisce l'esistenza di `raw/`, `book/`, `config/`.
    - Crea le sottocartelle sotto `raw/` secondo la sezione RAW dello YAML (se presente).
    - Se `context` non espone `raw_dir/book_dir/config_dir`, li imposta (stringhe assolute).
    - Idempotente.
    """
    slug = getattr(context, "slug", "client")
    base: Optional[Path] = None

    for attr in ("output_dir", "base_dir"):
        val = getattr(context, attr, None)
        if val:
            base = Path(val).resolve()
            break
    if base is None:
        base = Path(OUTPUT_DIR_NAME) / f"timmy-kb-{slug}"
        base = base.resolve()
    _ensure_dir(base)

    raw_dir = Path(getattr(context, "raw_dir", base / "raw")).resolve()
    book_dir = Path(getattr(context, "book_dir", getattr(context, "md_dir", base / "book"))).resolve()
    cfg_dir = Path(getattr(context, "config_dir", base / "config")).resolve()

    for d in (raw_dir, book_dir, cfg_dir):
        _ensure_dir(d)

    if not hasattr(context, "raw_dir"):
        try:
            setattr(context, "raw_dir", str(raw_dir))
        except Exception:
            pass
    if not hasattr(context, "book_dir"):
        try:
            setattr(context, "book_dir", str(book_dir))
        except Exception:
            pass
    if not hasattr(context, "config_dir"):
        try:
            setattr(context, "config_dir", str(cfg_dir))
        except Exception:
            pass

    struct = _read_yaml_structure(yaml_path)
    raw_mapping = struct.get("RAW") or struct.get("raw") or {}

    def _mk_children(base_path: Path, mapping: Dict[str, Any]) -> None:
        for raw_name, subtree in (mapping or {}).items():
            name = sanitize_filename(str(raw_name))
            child = base_path / name
            _ensure_dir(child)
            if isinstance(subtree, dict):
                _mk_children(child, subtree)
            elif isinstance(subtree, (list, tuple)):
                for leaf in subtree:
                    leaf_name = sanitize_filename(str(leaf))
                    _ensure_dir(child / leaf_name)
            else:
                pass

    _mk_children(raw_dir, raw_mapping)

    logger.info(
        "drive.upload.local_structure.created",
        extra={"raw_dir": str(raw_dir), "book_dir": str(book_dir), "config_dir": str(cfg_dir)},
    )


# ------------------------------- Delete -------------------------------------------


def delete_drive_file(service: Any, file_id: str) -> None:
    """Elimina un file per ID. Non solleva se il file non esiste (404)."""
    if not file_id:
        return
    _delete_file_hard(service, file_id)


# ------------------------------- Esportazioni -------------------------------------

__all__ = [
    "create_drive_folder",
    "create_drive_structure_from_yaml",
    "upload_config_to_drive_folder",
    "delete_drive_file",
    "create_local_base_structure",
]
