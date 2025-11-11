# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/upload.py
from __future__ import annotations

import os
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

from ..exceptions import ConfigError, DriveUploadError
from ..logging_utils import get_structured_logger
from ..path_utils import sanitize_filename

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


# ---------------------------------------------------------------------------
# YAML utils
# ---------------------------------------------------------------------------


def _normalize_yaml_structure(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict):
        if "root_folders" in data:
            raise ConfigError("Formato legacy 'root_folders' non supportato.")
        return data
    raise ConfigError("Struttura YAML non valida: atteso un dict.")


def _extract_structural_raw_names(mapping: Dict[str, Any]) -> List[str]:
    """Estrae i nomi delle categorie RAW di primo livello dal mapping moderno.

    Supporta sia:
      - {"raw": {"contracts": {}, "reports": {}}}
      - {"folders": [{"key": "contracts"}, {"key": "reports"}]}
    """
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

    # de-dup
    out: List[str] = []
    seen: set[str] = set()
    for n in names:
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _read_yaml_structure(yaml_path: Union[str, PathLike[str]]) -> Dict[str, Any]:
    p = Path(str(yaml_path))
    if not p.exists():
        raise ConfigError(f"File YAML di struttura non trovato: {yaml_path}")
    try:
        from ..yaml_utils import yaml_read

        data = yaml_read(p.parent, p) or {}
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"Impossibile leggere/parsing YAML: {e}") from e
    return _normalize_yaml_structure(data)


# ---------------------------------------------------------------------------
# Upload del config.yaml (fase 1)
# ---------------------------------------------------------------------------


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


def create_drive_raw_children_from_yaml(
    service: Any,
    yaml_path: Union[str, PathLike[str]],
    raw_parent_id: str,
    *,
    redact_logs: bool = False,
) -> Dict[str, str]:
    """Crea **solo** le sottocartelle immediate di `raw/` in Drive, leggendo lo YAML."""
    mapping = _read_yaml_structure(yaml_path)
    raw_names = _extract_structural_raw_names(mapping)

    result: Dict[str, str] = {}
    for name in raw_names:
        folder_id = create_drive_folder(service, name, raw_parent_id, redact_logs=redact_logs)
        result[name] = folder_id

    logger.info(
        "drive.upload.raw_children.created",
        extra={"raw_parent": _maybe_redact(raw_parent_id, redact_logs), "keys": list(result.keys())[:10]},
    )
    return result


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
    service: Any,
    yaml_path: Union[str, PathLike[str]],
    client_folder_id: str,
    *,
    redact_logs: bool = False,
) -> Dict[str, str]:
    """Crea la struttura Drive completa (raw + sottocartelle) usando un file YAML."""
    structure = create_drive_minimal_structure(service, client_folder_id, redact_logs=redact_logs)
    raw_id = structure.get("raw")
    if not raw_id:
        raise DriveUploadError("Creazione cartella RAW fallita: ID non reperito.")

    raw_children = create_drive_raw_children_from_yaml(
        service,
        yaml_path,
        raw_id,
        redact_logs=redact_logs,
    )

    combined: Dict[str, str] = {**structure}
    combined.update(raw_children)

    logger.info(
        "drive.upload.structure.yaml",
        extra={
            "client_folder": _maybe_redact(client_folder_id, redact_logs),
            "raw_children": list(raw_children.keys())[:10],
        },
    )
    return combined


# ---------------------------------------------------------------------------
# Locale: API di creazione cartelle (fase 2, children-only)
# ---------------------------------------------------------------------------


def create_local_raw_children_from_yaml(
    slug: str,
    yaml_path: Union[str, PathLike[str]],
    *,
    base_root: Union[str, Path] = "output",
) -> List[Path]:
    """Crea **solo** le sottocartelle immediate di `raw/` in locale, leggendo lo YAML."""
    mapping = _read_yaml_structure(yaml_path)
    raw_names = _extract_structural_raw_names(mapping)

    base_dir = Path(base_root) / f"timmy-kb-{slug}" / "raw"
    _ensure_dir(base_dir)

    written: List[Path] = []
    for name in raw_names:
        p = base_dir / name
        _ensure_dir(p)
        written.append(p)

    logger.info("local.raw_children.created", extra={"count": len(written), "base": str(base_dir)})
    return written


def create_local_base_structure(
    *,
    context: Any,
    yaml_structure_file: Union[str, PathLike[str]],
    base_root: Union[str, Path] = "output",
) -> Dict[str, Path]:
    """Crea la struttura locale (raw/, book/, config/, semantic/) e le sottocartelle raw/."""
    slug = getattr(context, "slug", None)
    if not isinstance(slug, str) or not slug:
        raise DriveUploadError("Contesto privo di slug: impossibile creare struttura locale.")

    base_dir_hint = getattr(context, "base_dir", None)
    base_dir = Path(str(base_dir_hint)) if base_dir_hint else Path(base_root) / f"timmy-kb-{slug}"
    base_dir = base_dir.resolve()

    raw_dir = base_dir / "raw"
    book_dir = base_dir / "book"
    config_dir = base_dir / "config"
    semantic_dir = base_dir / "semantic"

    _ensure_dir(base_dir)
    for path in (raw_dir, book_dir, config_dir, semantic_dir):
        _ensure_dir(path)

    mapping = _read_yaml_structure(yaml_structure_file)
    raw_names = _extract_structural_raw_names(mapping)
    for name in raw_names:
        _ensure_dir(raw_dir / name)

    logger.info(
        "local.base_structure.created",
        extra={
            "base": str(base_dir),
            "raw_children": raw_names[:10],
        },
    )
    return {
        "base_dir": base_dir,
        "raw_dir": raw_dir,
        "book_dir": book_dir,
        "config_dir": config_dir,
        "semantic_dir": semantic_dir,
    }


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
