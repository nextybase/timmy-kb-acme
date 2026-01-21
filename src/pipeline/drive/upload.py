# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/upload.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from ..exceptions import ConfigError, DriveUploadError
from ..logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.drive.upload")

_FOLDER_MIME = "application/vnd.google-apps.folder"
_META_KEYS: set[str] = {"title", "description", "examples", "note", "tags"}


# ---------------------------------------------------------------------------
# Helpers generali
# ---------------------------------------------------------------------------


def _maybe_redact(text: str, redact: bool) -> str:
    if not redact or not text:
        return text
    t = str(text)
    if len(t) <= 7:
        return "***"
    return f"{t[:3]}***{t[-3:]}"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _list_existing_folder_by_name(
    service: Any,
    parent_id: Optional[str],
    name: str,
) -> Optional[str]:
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

    from .client import _retry  # lazy import per evitare dipendenze circolari

    resp = cast(Dict[str, Any], _retry(_call, op_name="files.list.folder_by_name"))
    files = cast(List[Dict[str, Any]], resp.get("files", []))
    return cast(Optional[str], files[0]["id"] if files else None)


def _create_folder(service: Any, name: str, parent_id: Optional[str]) -> str:
    body: Dict[str, Any] = {"name": name, "mimeType": _FOLDER_MIME}
    if parent_id:
        body["parents"] = [parent_id]

    def _call() -> Any:
        return service.files().create(body=body, fields="id", supportsAllDrives=True).execute()

    from .client import _retry

    resp = cast(Dict[str, Any], _retry(_call, op_name="files.create.folder"))
    return cast(str, resp["id"])


def _delete_file_hard(service: Any, file_id: str) -> None:
    def _call() -> Any:
        return service.files().delete(fileId=file_id, supportsAllDrives=True).execute()

    from .client import _retry

    try:
        _retry(_call, op_name="files.delete")
    except Exception as e:  # noqa: BLE001
        status = getattr(getattr(e, "resp", None), "status", None)
        try:
            if status is not None and int(status) == 404:
                return
        except (TypeError, ValueError):
            pass
        raise


def _resolve_local_config_path(context: Any) -> Path:
    candidates: List[str] = []
    for attr in ("config_file", "config_path", "CONFIG_FILE", "CONFIG_PATH", "config_yaml_path", "client_config_file"):
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
    raise ConfigError("Impossibile individuare il file locale config.yaml nel contesto.")


def _find_existing_child_file_by_name(service: Any, parent_id: str, name: str) -> Optional[str]:
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

    from .client import _retry

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
            extra={"parent": _maybe_redact(parent_id, redact_logs), "old_id": _maybe_redact(existing_id, redact_logs)},
        )
        _delete_file_hard(service, existing_id)

    try:
        from googleapiclient.http import MediaFileUpload
    except Exception as e:  # noqa: BLE001
        raise DriveUploadError(
            "Dipendenza mancante per upload su Drive: google-api-python-client. Installa con `pip install .[drive]`."
        ) from e

    media = MediaFileUpload(str(local_config), mimetype="application/octet-stream", resumable=False)
    body = {"name": "config.yaml", "parents": [parent_id]}

    def _call() -> Any:
        return service.files().create(body=body, media_body=media, fields="id", supportsAllDrives=True).execute()

    from .client import _retry

    try:
        resp = cast(Dict[str, Any], _retry(_call, op_name="files.create.config"))
    except Exception as e:  # noqa: BLE001
        local_logger.error(
            "drive.upload.config.error",
            extra={
                "parent": _maybe_redact(parent_id, redact_logs),
                "local": str(local_config),
                "error_message": str(e)[:300],
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


# ---------------------------------------------------------------------------
# Drive: API di creazione cartelle (fase 2, children-only)
# ---------------------------------------------------------------------------


def create_drive_folder(
    service: Any,
    name: str,
    parent_id: Optional[str] = None,
    *,
    redact_logs: bool = False,
) -> str:
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
                "error_message": str(e)[:300],
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


def create_drive_minimal_structure(
    service: Any,
    client_folder_id: str,
    *,
    redact_logs: bool = False,
) -> Dict[str, str]:
    """Crea la struttura minima (cartelle top-level) sotto la cartella cliente."""
    if not client_folder_id:
        raise DriveUploadError("ID cartella cliente mancante per struttura minima.")

    structure: Dict[str, str] = {}
    for name in ("raw", "contrattualistica"):
        structure[name] = create_drive_folder(service, name, client_folder_id, redact_logs=redact_logs)

    logger.info(
        "drive.upload.structure.minimal",
        extra={
            "client_folder": _maybe_redact(client_folder_id, redact_logs),
            "folders": list(structure.keys()),
        },
    )
    return structure


def create_drive_structure_from_yaml(
    *,
    ctx: Any,
    yaml_path: Path,
    parent_folder_id: str,
    log: Any | None = None,
    redact_logs: bool = False,
) -> Dict[str, str]:
    """Crea le sottocartelle Drive a partire da un file YAML (raw structure)."""
    raise RuntimeError(
        "create_drive_structure_from_yaml è disabilitato in Beta 1.0. "
        "Usa create_drive_structure_from_names con nomi derivati da semantic_mapping.yaml."
    )


def create_drive_structure_from_names(
    *,
    ctx: Any,
    folder_names: List[str],
    parent_folder_id: str,
    log: Any | None = None,
    redact_logs: bool = False,
) -> Dict[str, str]:
    """Crea (o riusa) sottocartelle Drive sotto parent_folder_id a partire da una lista di nomi.

    - Nessun file intermedio.
    - Idempotente (riusa se già esiste).
    - Ordinamento deterministico.
    """
    if not parent_folder_id:
        raise DriveUploadError("Parent ID mancante per struttura da nomi.")
    if not isinstance(folder_names, list):
        raise ConfigError("folder_names deve essere una lista.")

    from .client import get_drive_service

    service = get_drive_service(ctx)
    local_logger = log if log is not None else logger

    cleaned: List[str] = []
    for name in folder_names:
        if isinstance(name, str) and name.strip():
            cleaned.append(name.strip())

    cleaned = sorted(set(cleaned))

    created: Dict[str, str] = {}
    for folder_name in cleaned:
        created[folder_name] = create_drive_folder(
            service,
            folder_name,
            parent_folder_id,
            redact_logs=redact_logs,
        )

    local_logger.info(
        "drive.upload.structure.names",
        extra={
            "parent": _maybe_redact(parent_folder_id, redact_logs),
            "folders": list(created.keys()),
        },
    )
    return created


def delete_drive_file(
    service: Any,
    file_id: str,
    *,
    redact_logs: bool = False,
) -> None:
    """Elimina un file/cartella su Drive (idempotente su 404)."""
    if not file_id:
        raise DriveUploadError("File ID mancante per eliminazione.")

    try:
        _delete_file_hard(service, file_id)
    except Exception as exc:  # noqa: BLE001
        raise DriveUploadError(f"Eliminazione file Drive fallita: {file_id}") from exc

    logger.info(
        "drive.upload.file.deleted",
        extra={"file_id": _maybe_redact(file_id, redact_logs)},
    )
