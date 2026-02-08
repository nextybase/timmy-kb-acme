# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.config_utils import get_drive_id
from pipeline.context import ClientContext, validate_slug
from pipeline.env_constants import WORKSPACE_ROOT_ENV
from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.yaml_utils import yaml_read
from ui import clients_store

try:
    from pipeline.drive_utils import delete_drive_file, get_drive_service
except Exception:  # pragma: no cover - dipendenze Drive opzionali
    delete_drive_file = None
    get_drive_service = None


def _resolve_workspace_root(slug: str) -> Path:
    """Risoluzione workspace: WORKSPACE_ROOT_DIR obbligatorio e deve puntare a .../timmy-kb-<slug>."""
    expected = f"timmy-kb-{slug}"
    try:
        raw = get_env_var(WORKSPACE_ROOT_ENV, required=True)
    except ConfigError as exc:
        raise ConfigError(
            f"{WORKSPACE_ROOT_ENV} obbligatorio: {exc}",
            slug=slug,
            code="workspace.root.invalid",
            component="tools.clean_client_workspace",
        ) from exc
    raw_value = str(raw)
    if "<slug>" in raw_value:
        raw_value = raw_value.replace("<slug>", slug)

    if "?" in raw_value or "#" in raw_value:
        raise ConfigError(
            f"{WORKSPACE_ROOT_ENV} contiene caratteri non validi: {raw_value}",
            slug=slug,
            code="workspace.root.invalid",
            component="tools.clean_client_workspace",
        )

    try:
        root = Path(raw_value).expanduser().resolve()
    except Exception as exc:
        raise ConfigError(
            f"{WORKSPACE_ROOT_ENV} non valido: {raw}",
            slug=slug,
            code="workspace.root.invalid",
            component="tools.clean_client_workspace",
        ) from exc
    if root.name != expected:
        raise ConfigError(
            f"{WORKSPACE_ROOT_ENV} deve puntare direttamente a '.../{expected}' (trovato: {root})",
            slug=slug,
            code="workspace.root.invalid",
            component="tools.clean_client_workspace",
        )
    return root


def _load_config_payload(config_path: Path, *, workspace_root: Path, slug: str) -> Dict[str, Any]:
    try:
        raw = yaml_read(workspace_root, config_path, encoding="utf-8", use_cache=False)
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(f"Lettura config.yaml fallita: {exc}", slug=slug, file_path=str(config_path)) from exc
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml non valido: atteso mapping.", slug=slug, file_path=str(config_path))
    return dict(raw)


def _require_drive_root_id(config: Dict[str, Any], *, slug: str, config_path: Path) -> str:
    value = get_drive_id(config, "folder_id")
    if not value:
        raise ConfigError(
            "ID Drive mancante in config.yaml: integrations.drive.folder_id",
            slug=slug,
            file_path=str(config_path),
        )
    return value


def _should_skip_drive_cleanup(config: Dict[str, Any]) -> bool:
    ui_section = config.get("ui")
    ui_allow_local_only = bool(ui_section.get("allow_local_only")) if isinstance(ui_section, dict) else False
    if ui_allow_local_only:
        return True
    missing_env = not get_env_var("DRIVE_ID") or not get_env_var("SERVICE_ACCOUNT_FILE")
    return missing_env


def _require_drive_utils() -> None:
    if not callable(get_drive_service) or not callable(delete_drive_file):
        raise ConfigError("Dipendenze Drive non disponibili: installa gli extra Drive (pip install .[drive]).")


def _remove_registry_entry(slug: str) -> tuple[bool, Optional[str]]:
    try:
        entries = clients_store.load_clients()
        remaining = [e for e in entries if e.slug.strip().lower() != slug.strip().lower()]
        if len(remaining) == len(entries):
            return False, None
        clients_store.save_clients(remaining)
        return True, None
    except Exception as exc:
        return False, f"registry_remove_failed: {exc}"


def _clear_ui_state(slug: str) -> tuple[bool, Optional[str]]:
    path = clients_store.get_ui_state_path()
    if not path.exists():
        return False, None
    try:
        raw_text = read_text_safe(path.parent, path, encoding="utf-8")
        payload = json.loads(raw_text or "{}")
        if not isinstance(payload, dict):
            raise ConfigError("ui_state.json non valido: atteso mapping.")
        current = str(payload.get("active_slug") or "").strip().lower()
        if current != slug.strip().lower():
            return False, None
        payload["active_slug"] = ""
        safe_write_text(path, json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8", atomic=True)
        return True, None
    except Exception as exc:
        return False, f"ui_state_clear_failed: {exc}"


def _remove_semantic_progress(slug: str) -> tuple[bool, Optional[str]]:
    db_dir, _ = clients_store.get_registry_paths()
    target = ensure_within_and_resolve(db_dir, db_dir / "semantic_progress" / f"{slug}.json")
    if not target.exists():
        return False, None
    try:
        target.unlink()
        return True, None
    except Exception as exc:
        return False, f"semantic_progress_remove_failed: {exc}"


def _remove_ownership(slug: str) -> tuple[bool, Optional[str]]:
    db_dir, _ = clients_store.get_registry_paths()
    target = ensure_within_and_resolve(db_dir, db_dir / "clients" / slug)
    if not target.exists():
        return False, None
    try:
        shutil.rmtree(target, ignore_errors=False)
        return True, None
    except Exception as exc:
        return False, f"ownership_remove_failed: {exc}"


def _remove_workspace_dir(workspace_root: Path) -> tuple[bool, Optional[str]]:
    target = ensure_within_and_resolve(workspace_root, workspace_root)
    if not target.exists():
        return True, None
    try:
        shutil.rmtree(target, ignore_errors=False)
        return True, None
    except Exception as exc:
        return False, f"workspace_remove_failed: {exc}"


def perform_cleanup(slug: str, *, client_name: Optional[str] = None) -> Dict[str, Any]:
    """Esegue cleanup locale + registry + Drive. Ritorna un report con exit_code."""
    validate_slug(slug)
    logger = get_structured_logger("tools.clean_client_workspace", context={"slug": slug})

    workspace_root = _resolve_workspace_root(slug)
    drive_error: Optional[str] = None
    drive_deleted = False
    drive_root_id: Optional[str] = None

    config_path = ensure_within_and_resolve(workspace_root, workspace_root / "config" / "config.yaml")
    if config_path.exists():
        try:
            config_payload = _load_config_payload(config_path, workspace_root=workspace_root, slug=slug)
            try:
                drive_root_id = _require_drive_root_id(config_payload, slug=slug, config_path=config_path)
            except ConfigError as exc:
                if _should_skip_drive_cleanup(config_payload):
                    logger.info(
                        "tools.clean_client_workspace.drive_skipped",
                        extra={"slug": slug, "reason": "missing_drive_id"},
                    )
                else:
                    raise exc
        except Exception as exc:
            drive_error = f"drive_config_invalid: {exc}"
    else:
        drive_error = "missing_config_yaml"

    if drive_root_id and drive_error is None:
        try:
            _require_drive_utils()
            context = ClientContext.load(slug=slug, require_drive_env=True, bootstrap_config=False)
            service = get_drive_service(context)
            delete_drive_file(service, drive_root_id, redact_logs=bool(context.redact_logs))
            drive_deleted = True
        except Exception as exc:
            drive_error = str(exc)
            logger.warning("tools.clean_client_workspace.drive_failed", extra={"slug": slug, "error": drive_error})

    errors: list[str] = []
    registry_removed, registry_err = _remove_registry_entry(slug)
    if registry_err:
        errors.append(registry_err)
    ui_state_cleared, ui_state_err = _clear_ui_state(slug)
    if ui_state_err:
        errors.append(ui_state_err)
    semantic_progress_removed, semantic_err = _remove_semantic_progress(slug)
    if semantic_err:
        errors.append(semantic_err)
    ownership_removed, ownership_err = _remove_ownership(slug)
    if ownership_err:
        errors.append(ownership_err)
    local_removed, local_err = _remove_workspace_dir(workspace_root)
    if local_err:
        errors.append(local_err)

    if local_err:
        exit_code = 4
    elif drive_error:
        exit_code = 3
    elif errors:
        exit_code = 2
    else:
        exit_code = 0

    return {
        "exit_code": exit_code,
        "slug": slug,
        "client_name": client_name,
        "drive_deleted": drive_deleted,
        "drive_error": drive_error,
        "drive_root_id": drive_root_id,
        "registry_removed": registry_removed,
        "ui_state_cleared": ui_state_cleared,
        "semantic_progress_removed": semantic_progress_removed,
        "ownership_removed": ownership_removed,
        "local_removed": local_removed,
        "errors": errors,
    }


def run_cleanup(slug: str, assume_yes: bool = True) -> int:
    """Compat CLI: ritorna exit_code senza prompt."""
    if not assume_yes:
        raise ConfigError("Modalita interattiva non supportata in tools.clean_client_workspace.")
    result = perform_cleanup(slug)
    return int(result.get("exit_code", 1))


__all__ = ["perform_cleanup", "run_cleanup"]
