from __future__ import annotations

from googleapiclient.errors import HttpError

# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/upload.py
"""
Operazioni di creazione/aggiornamento su Google Drive e struttura locale.

# Panoramica & ruoli delle funzioni

Questa unità fornisce la superficie pubblica per le operazioni "write" lato Drive
e per il bootstrap della struttura locale. È richiamata tramite `pipeline.drive_utils`
e mantiene la compatibilità con il monolite precedente.

## API principali

- create_drive_folder(service, name, parent_id=None, *, redact_logs=False) -> str
  Idempotente: se la cartella esiste sotto `parent_id` riusa l'ID, altrimenti la crea.

- create_drive_structure_from_yaml(service, yaml_path, client_folder_id, *, redact_logs=False) -> dict[str, str]
  Costruisce ricorsivamente l’albero di cartelle remoto partendo da uno YAML nel **formato moderno**
  (mapping {nome: sottoalbero}). Ritorna una mappa nome→ID.

- upload_config_to_drive_folder(service, context, parent_id, *, redact_logs=False) -> str
  Carica (sostituzione sicura) `config.yaml` nella cartella cliente su Drive. Se presente
  elimina la versione precedente. Redige gli ID nei log se richiesto.

- delete_drive_file(service, file_id) -> None
  Elimina un file da Drive; ignora 404 per idempotenza.

- create_local_base_structure(context, yaml_path) -> None
  Crea la struttura **locale** minima (raw/, book/, config/) e popola raw/ secondo
  la sezione RAW dello YAML. Se il `context` non espone `raw_dir`/`book_dir`/`config_dir`,
  li inizializza come `Path` assoluti.

## Convenzioni & sicurezza

- Compatibilità Shared Drives (supportsAllDrives=True).
- Idempotenza su creazione cartelle e upload config.
- Logging strutturato (nessun print) con supporto alla redazione (`redact_logs`).
- La guardia STRONG sui path (SSoT) resta in `pipeline.path_utils.ensure_within`;
  qui si assume che gli orchestratori abbiano validato i perimetri di scrittura.
"""

import os
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

from ..constants import OUTPUT_DIR_NAME
from ..exceptions import ConfigError, DriveUploadError
from ..logging_utils import get_structured_logger
from ..path_utils import sanitize_filename
from .client import _retry

# Logger di modulo (fallback). Dove possibile, useremo un logger contestualizzato locale.
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


def _list_existing_folder_by_name(
    service: Any, parent_id: Optional[str], name: str
) -> Optional[str]:
    """
    Ritorna l'ID di una cartella già esistente con `name` sotto `parent_id`, se presente.
    Se `parent_id` è None, cerca a livello "root" dell'utente/service account.
    """
    base = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q = f"{base} and '{parent_id}' in parents and name = '{name}'"
    else:
        q = f"{base} and name = '{name}'"

    def _call() -> Any:
        req = service.files().list(
            q=q,
            spaces="drive",
            fields="files(id, name)",
            pageSize=10,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        return req.execute()

    resp = cast(Dict[str, Any], _retry(_call, op_name="files.list.folder_by_name"))
    files = cast(List[Dict[str, Any]], resp.get("files", []))
    if not files:
        return None
    return cast(str, files[0]["id"])  # id è atteso stringa


def _create_folder(service: Any, name: str, parent_id: Optional[str]) -> str:
    """
    Crea una cartella su Drive e ritorna l'ID.
    Non esegue lookup: la responsabilità di idempotenza è nel chiamante.
    """
    body: Dict[str, Any] = {"name": name, "mimeType": _FOLDER_MIME}
    if parent_id:
        body["parents"] = [parent_id]

    def _call() -> Any:
        return service.files().create(body=body, fields="id", supportsAllDrives=True).execute()

    resp = cast(Dict[str, Any], _retry(_call, op_name="files.create.folder"))
    return cast(str, resp["id"])  # ID previsto stringa


def _delete_file_hard(service: Any, file_id: str) -> None:
    """Elimina un file su Drive; ignora il 404 (già non presente)."""

    def _call() -> Any:
        return service.files().delete(fileId=file_id, supportsAllDrives=True).execute()

    try:
        _retry(_call, op_name="files.delete")
    except HttpError as e:
        try:
            status = int(e.resp.status)
        except Exception:
            status = None
        if status == 404:
            return
        raise


# ------------------------------- Normalizzazione YAML -----------------------------


def _normalize_yaml_structure(data: Any) -> Dict[str, Any]:
    """
    Normalizza la struttura YAML della gerarchia remota in un **mapping annidato**.

    Formati supportati:
    1) **Moderno**: dict con chiavi qualsiasi (es. RAW/YAML o categorie libere).
       Il formato legacy con `root_folders` **non è supportato** in v1.8.0.
    2) **Fallback permissivo**: se è un dict che non contiene RAW/YAML, viene usato
       così com'è (nessun errore).
    """
    if isinstance(data, dict):
        # v1.8.0: formato legacy NON supportato
        if "root_folders" in data:
            raise ConfigError(
                "Formato legacy 'root_folders' non supportato in v1.8.0. "
                "Fornire un mapping {nome: sottoalbero} moderno."
            )
        # Moderno/generico: accetta il dict così com'è
        return data

    raise ConfigError("Struttura YAML non valida: atteso un mapping (dict).")


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
                "folder_name": name,  # ⚠️ niente chiave 'name'
                "folder_id": _maybe_redact(existing, redact_logs),
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
                "folder_name": name,  # ⚠️ niente chiave 'name'
                "message": str(e)[:300],
            },
        )
        raise DriveUploadError(f"Creazione cartella fallita: {name}") from e

    logger.info(
        "drive.upload.folder.created",
        extra={
            "parent": _maybe_redact(parent_id or "root", redact_logs),
            "folder_name": name,  # ⚠️ niente chiave 'name'
            "folder_id": _maybe_redact(new_id, redact_logs),
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
            _create_remote_tree_from_mapping(
                service, folder_id, subtree, redact_logs=redact_logs, result=result
            )
        elif isinstance(subtree, (list, tuple)):
            for leaf in subtree:
                leaf_name = sanitize_filename(str(leaf))
                leaf_id = create_drive_folder(
                    service, leaf_name, folder_id, redact_logs=redact_logs
                )
                result[leaf_name] = leaf_id
        else:
            # foglia vuota / valore non strutturato: nessuna sotto-cartella
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

    Comportamento (v1.8.0):
    - Accetta solo struttura **moderna**: mapping {nome: sottoalbero}; il formato legacy
      con `root_folders` non è supportato.
    - Ritorna una mappa nome→ID. Nessun alias aggiunto.
    """
    if not os.path.isfile(str(yaml_path)):
        raise ConfigError(f"File YAML di struttura non trovato: {yaml_path}")

    try:
        from ..yaml_utils import yaml_read

        p = Path(str(yaml_path))
        data = yaml_read(p.parent, p) or {}
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"Impossibile leggere/parsing YAML: {e}") from e

    mapping = _normalize_yaml_structure(data)

    result: Dict[str, str] = {}
    _create_remote_tree_from_mapping(
        service, client_folder_id, mapping, redact_logs=redact_logs, result=result
    )

    # v1.8.0: nessun alias nel risultato

    logger.info(
        "drive.upload.tree.created",
        extra={
            "client_root": _maybe_redact(client_folder_id, redact_logs),
            "keys": list(result.keys())[:10],
        },
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
        dir_path = context.config_dir
        if dir_path:
            candidates.append(os.path.join(str(dir_path), "config.yaml"))

    if hasattr(context, "client_dir"):
        base = context.client_dir
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

    def _call() -> Any:
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
    files = cast(List[Dict[str, Any]], resp.get("files", []))
    if not files:
        return None
    return cast(str, files[0]["id"])  # id stringa


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

    # Logger contestualizzato + redazione auto-derivata dal contesto (come in download.py)
    local_logger = (
        get_structured_logger("pipeline.drive.upload", context=context) if context else logger
    )
    redact_logs = bool(
        redact_logs or (getattr(context, "redact_logs", False) if context is not None else False)
    )

    local_config = _resolve_local_config_path(context)
    if not local_config.is_file():
        raise DriveUploadError(f"File locale non trovato: {local_config}")

    existing_id = _find_existing_child_file_by_name(service, parent_id, "config.yaml")
    if existing_id:
        local_logger.info(
            "drive.upload.config.replace",
            extra={
                "parent": _maybe_redact(parent_id, redact_logs),
                "old_id": _maybe_redact(existing_id, redact_logs),
            },
        )
        _delete_file_hard(service, existing_id)

    # Lazy import: disponibile solo se effettivamente carichiamo il file
    try:
        from googleapiclient.http import MediaFileUpload
    except Exception as e:  # noqa: BLE001
        raise DriveUploadError(
            "Dipendenza mancante per upload su Drive: google-api-python-client. "
            "Installa la libreria o usa --dry-run."
        ) from e

    media = MediaFileUpload(str(local_config), mimetype="application/octet-stream", resumable=False)
    body = {"name": "config.yaml", "parents": [parent_id]}

    def _call() -> Any:
        return (
            service.files()
            .create(body=body, media_body=media, fields="id", supportsAllDrives=True)
            .execute()
        )

    try:
        resp = cast(Dict[str, Any], _retry(_call, op_name="files.create.config"))
    except Exception as e:  # noqa: BLE001
        local_logger.error(
            "drive.upload.config.error",
            extra={
                "parent": _maybe_redact(parent_id, redact_logs),
                "local": str(local_config),
                "message": str(e)[:300],
            },
        )
        raise DriveUploadError(f"Upload config.yaml fallito: {e}") from e

    file_id = cast(str, resp["id"])  # id è stringa
    local_logger.info(
        "drive.upload.config.done",
        extra={
            "parent": _maybe_redact(parent_id, redact_logs),
            "file_id": _maybe_redact(file_id, redact_logs),
            "local": str(local_config),
        },
    )
    return file_id


# ------------------------------- Struttura LOCALE (permissiva) --------------------


def _read_yaml_structure(yaml_path: Union[str, PathLike[str]]) -> Dict[str, Any]:
    """Carica il file YAML e ritorna la struttura normalizzata (vedi _normalize_yaml_structure)."""
    p = Path(str(yaml_path))
    if not p.exists():
        raise ConfigError(f"File YAML di struttura non trovato: {yaml_path}")
    try:
        from ..yaml_utils import yaml_read

        data = yaml_read(p.parent, p) or {}
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
    - Se `context` non espone `raw_dir`/`book_dir`/`config_dir`, li imposta come `Path` assoluti.
    - Idempotente.
    """
    # Logger contestualizzato per uniformità con gli orchestratori
    local_logger = (
        get_structured_logger("pipeline.drive.upload", context=context) if context else logger
    )

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
    book_dir = Path(
        getattr(context, "book_dir", getattr(context, "md_dir", base / "book"))
    ).resolve()
    cfg_dir = Path(getattr(context, "config_dir", base / "config")).resolve()

    for d in (raw_dir, book_dir, cfg_dir):
        _ensure_dir(d)

    if not hasattr(context, "raw_dir"):
        try:
            context.raw_dir = raw_dir
        except Exception:
            pass
    if not hasattr(context, "book_dir"):
        try:
            context.book_dir = book_dir
        except Exception:
            pass
    if not hasattr(context, "config_dir"):
        try:
            context.config_dir = cfg_dir
        except Exception:
            pass

    struct = _read_yaml_structure(yaml_path)
    raw_mapping = struct.get("raw") or {}

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

    local_logger.info(
        "drive.upload.local_structure.created",
        extra={
            "raw_dir": str(raw_dir),
            "book_dir": str(book_dir),
            "config_dir": str(cfg_dir),
        },
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
