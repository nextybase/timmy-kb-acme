from __future__ import annotations

from googleapiclient.errors import HttpError

# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/upload.py
"""
Operazioni di creazione/aggiornamento su Google Drive e struttura locale.

Principi chiave:

- In Drive, alla root cliente creiamo SOLO `raw/` e `contrattualistica/`.
- Sotto `raw/` creiamo una cartella per ogni categoria strutturale dallo YAML.
- In locale, creiamo solo le categorie di primo livello (niente title/description/examples).
- Dove possibile preferiamo sempre lo YAML del cliente:
  `<output>/timmy-kb-<slug>/semantic/cartelle_raw.yaml`.
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

logger = get_structured_logger("pipeline.drive.upload")

_FOLDER_MIME = "application/vnd.google-apps.folder"
_META_KEYS: set[str] = {"title", "description", "examples", "note", "tags"}

# --------------------------------- Utilità ---------------------------------


def _maybe_redact(text: str, redact: bool) -> str:
    """Oscura una stringa nei log quando `redact` è attivo."""
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
    service: Any,
    parent_id: Optional[str],
    name: str,
) -> Optional[str]:
    """Ritorna l'ID di una cartella `name` già esistente sotto `parent_id` (se presente)."""
    base = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    q = f"{base} and '{parent_id}' in parents and name = '{name}'" if parent_id else f"{base} and name = '{name}'"

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
    return cast(Optional[str], files[0]["id"] if files else None)


def _create_folder(service: Any, name: str, parent_id: Optional[str]) -> str:
    """Crea una cartella e ritorna l'ID (nessun controllo di idempotenza)."""
    body: Dict[str, Any] = {"name": name, "mimeType": _FOLDER_MIME}
    if parent_id:
        body["parents"] = [parent_id]

    def _call() -> Any:
        return service.files().create(body=body, fields="id", supportsAllDrives=True).execute()

    resp = cast(Dict[str, Any], _retry(_call, op_name="files.create.folder"))
    return cast(str, resp["id"])


def _delete_file_hard(service: Any, file_id: str) -> None:
    """Elimina un file su Drive; ignora il 404."""

    def _call() -> Any:
        return service.files().delete(fileId=file_id, supportsAllDrives=True).execute()

    try:
        _retry(_call, op_name="files.delete")
    except HttpError as e:
        status: Optional[int] = None
        try:
            status = int(e.resp.status)
        except Exception:
            pass
        if status != 404:
            raise


# --------------------------------- YAML ------------------------------------


def _normalize_yaml_structure(data: Any) -> Dict[str, Any]:
    """Valida/normalizza lo YAML della gerarchia remota in un mapping annidato."""
    if isinstance(data, dict):
        if "root_folders" in data:
            raise ConfigError("Formato legacy 'root_folders' non supportato: usare mapping {nome: sottoalbero}.")
        return data
    raise ConfigError("Struttura YAML non valida: atteso un mapping (dict).")


def _extract_structural_raw_names(mapping: Dict[str, Any]) -> List[str]:
    """Estrae i nomi delle categorie RAW di primo livello (senza meta-chiavi)."""
    names: List[str] = []

    if isinstance(mapping.get("raw"), dict):
        for k in mapping["raw"].keys():
            names.append(sanitize_filename(str(k)))

    if not names and isinstance(mapping.get("folders"), list):
        for item in mapping["folders"]:
            if isinstance(item, dict):
                key = item.get("key") or item.get("name")
                if key:
                    names.append(sanitize_filename(str(key)))

    seen: set[str] = set()
    deduped: List[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped


# ------------------------------- API Drive ---------------------------------


def create_drive_folder(
    service: Any,
    name: str,
    parent_id: Optional[str] = None,
    *,
    redact_logs: bool = False,
) -> str:
    """Crea (idempotente) la cartella `name` sotto `parent_id` e ritorna l'ID."""
    if not name:
        raise DriveUploadError("Nome cartella mancante.")

    existing = _list_existing_folder_by_name(service, parent_id, name)
    if existing:
        logger.info(
            "drive.upload.folder.reuse",
            extra={
                "parent": _maybe_redact(parent_id or "root", redact_logs),
                "folder_name": name,
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
                "folder_name": name,
                "message": str(e)[:300],
            },
        )
        raise DriveUploadError(f"Creazione cartella fallita: {name}") from e

    logger.info(
        "drive.upload.folder.created",
        extra={
            "parent": _maybe_redact(parent_id or "root", redact_logs),
            "folder_name": name,
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
    """Crea ricorsivamente un albero di cartelle da mapping {nome: sottoalbero}."""
    if result is None:
        result = {}

    for raw_name, subtree in (mapping or {}).items():
        name = sanitize_filename(str(raw_name))
        folder_id = create_drive_folder(service, name, parent_id, redact_logs=redact_logs)
        result[name] = folder_id

        if isinstance(subtree, dict):
            structural_children = {k: v for k, v in subtree.items() if k not in _META_KEYS}
            if structural_children:
                _create_remote_tree_from_mapping(
                    service,
                    folder_id,
                    structural_children,
                    redact_logs=redact_logs,
                    result=result,
                )
    return result


def create_drive_structure_from_yaml(
    service: Any,
    yaml_path: Union[str, PathLike[str]],
    client_folder_id: str,
    *,
    redact_logs: bool = False,
) -> Dict[str, str]:
    """Crea la struttura remota a partire da file YAML (formato moderno)."""
    if not os.path.isfile(str(yaml_path)):
        raise ConfigError(f"File YAML di struttura non trovato: {yaml_path}")

    try:
        from ..yaml_utils import yaml_read

        p = Path(str(yaml_path))
        data = yaml_read(p.parent, p) or {}
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"Impossibile leggere/parsing YAML: {e}") from e

    mapping = _normalize_yaml_structure(data)
    raw_names = _extract_structural_raw_names(mapping)

    result: Dict[str, str] = {}
    raw_root_id = create_drive_folder(
        service,
        "raw",
        client_folder_id,
        redact_logs=redact_logs,
    )
    result["raw"] = raw_root_id

    contr_id = create_drive_folder(
        service,
        "contrattualistica",
        client_folder_id,
        redact_logs=redact_logs,
    )
    result["contrattualistica"] = contr_id

    for name in raw_names:
        folder_id = create_drive_folder(
            service,
            name,
            raw_root_id,
            redact_logs=redact_logs,
        )
        result[name] = folder_id

    logger.info(
        "drive.upload.tree.created",
        extra={
            "client_root": _maybe_redact(client_folder_id, redact_logs),
            "keys": list(result.keys())[:10],
        },
    )
    return result


# ----------------------------- Upload config --------------------------------


def _resolve_local_config_path(context: Any) -> Path:
    """Tenta varie convenzioni per trovare il `config.yaml` locale del cliente."""
    candidates: List[str] = []
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
        dir_path = getattr(context, "config_dir", None)
        if dir_path:
            candidates.append(os.path.join(str(dir_path), "config.yaml"))

    if hasattr(context, "client_dir"):
        base = getattr(context, "client_dir", None)
        if base:
            candidates.append(os.path.join(str(base), "config", "config.yaml"))

    for cand in candidates:
        p = Path(os.path.expanduser(str(cand))).resolve()
        if p.is_file():
            return p

    raise ConfigError("Impossibile individuare il file locale config.yaml nel contesto fornito.")


def _find_existing_child_file_by_name(
    service: Any,
    parent_id: str,
    name: str,
) -> Optional[str]:
    """Ritorna l'ID del file figlio chiamato `name` sotto `parent_id` (se esiste)."""
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
    return cast(Optional[str], files[0]["id"] if files else None)


def upload_config_to_drive_folder(
    service: Any,
    context: Any,
    parent_id: str,
    *,
    redact_logs: bool = False,
) -> str:
    """Carica `config.yaml` nella cartella cliente (sostituzione sicura)."""
    if not parent_id:
        raise DriveUploadError("Parent ID mancante per upload config.")

    local_logger = get_structured_logger("pipeline.drive.upload", context=context) if context else logger
    redact_logs = bool(redact_logs or getattr(context, "redact_logs", False))

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

    try:
        from googleapiclient.http import MediaFileUpload
    except Exception as e:  # noqa: BLE001
        raise DriveUploadError(
            "Dipendenza mancante per upload su Drive: google-api-python-client. "
            "Installa la libreria o usa --dry-run."
        ) from e

    media = MediaFileUpload(
        str(local_config),
        mimetype="application/octet-stream",
        resumable=False,
    )
    body = {"name": "config.yaml", "parents": [parent_id]}

    def _call() -> Any:
        return (
            service.files()
            .create(
                body=body,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
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

    file_id = cast(str, resp["id"])
    local_logger.info(
        "drive.upload.config.done",
        extra={
            "parent": _maybe_redact(parent_id, redact_logs),
            "file_id": _maybe_redact(file_id, redact_logs),
            "local": str(local_config),
        },
    )
    return file_id


# --------------------------- Struttura locale --------------------------------


def _read_yaml_structure(yaml_path: Union[str, PathLike[str]]) -> Dict[str, Any]:
    """Carica lo YAML e ritorna la struttura normalizzata."""
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
    Crea la struttura LOCALE di base.

    - Base dir: context.output_dir | context.base_dir | output/timmy-kb-<slug>
    - Crea raw/, book/, config/.
    - Popola **solo** le categorie di primo livello sotto raw/ ricavate dallo YAML.
    - **Preferisce sempre lo YAML del cliente**: <base>/semantic/cartelle_raw.yaml (se esiste).
    """
    local_logger = get_structured_logger("pipeline.drive.upload", context=context) if context else logger

    slug = getattr(context, "slug", "client")
    base: Optional[Path] = None

    for attr in ("output_dir", "base_dir"):
        val = getattr(context, attr, None)
        if val:
            base = Path(val).resolve()
            break
    if base is None:
        base = (Path(OUTPUT_DIR_NAME) / f"timmy-kb-{slug}").resolve()
    _ensure_dir(base)

    raw_dir = Path(getattr(context, "raw_dir", base / "raw")).resolve()
    book_dir = Path(getattr(context, "book_dir", getattr(context, "md_dir", base / "book"))).resolve()
    cfg_dir = Path(getattr(context, "config_dir", base / "config")).resolve()

    for d in (raw_dir, book_dir, cfg_dir):
        _ensure_dir(d)

    # Esporta i path nel contesto se mancano
    for attr, val in (("raw_dir", raw_dir), ("book_dir", book_dir), ("config_dir", cfg_dir)):
        if not hasattr(context, attr):
            try:
                setattr(context, attr, val)
            except Exception:
                pass

    # Preferisci YAML del cliente, ignora quello generale se il primo esiste
    client_yaml = base / "semantic" / "cartelle_raw.yaml"
    chosen_yaml = client_yaml if client_yaml.exists() else Path(str(yaml_path))

    struct = _read_yaml_structure(chosen_yaml)
    raw_names = _extract_structural_raw_names(struct)

    for name in raw_names:
        _ensure_dir(raw_dir / name)

    local_logger.info(
        "drive.upload.local_structure.created",
        extra={
            "raw_dir": str(raw_dir),
            "book_dir": str(book_dir),
            "config_dir": str(cfg_dir),
            "yaml_used": str(chosen_yaml),
        },
    )


# --------------------------------- Delete ----------------------------------


def delete_drive_file(service: Any, file_id: str) -> None:
    """Elimina un file per ID (idempotente)."""
    if not file_id:
        return
    _delete_file_hard(service, file_id)


# ------------------------------- Esportazioni --------------------------------


def create_drive_minimal_structure(service: Any, client_folder_id: str, *, redact_logs: bool = False) -> Dict[str, str]:
    """
    Crea SOLO l'ossatura minima su Drive:
      - raw/
      - contrattualistica/
    sotto la cartella cliente. Non legge YAML.
    Ritorna: {"raw": <id>, "contrattualistica": <id>}
    """
    raw_id = create_drive_folder(service, "raw", client_folder_id, redact_logs=redact_logs)
    contr_id = create_drive_folder(service, "contrattualistica", client_folder_id, redact_logs=redact_logs)
    logger.info("drive.upload.minimal.created", extra={"client_root": _maybe_redact(client_folder_id, redact_logs)})
    return {"raw": raw_id, "contrattualistica": contr_id}


__all__ = [
    "create_drive_folder",
    "create_drive_structure_from_yaml",
    "upload_config_to_drive_folder",
    "delete_drive_file",
    "create_local_base_structure",
    "create_drive_minimal_structure",
]
