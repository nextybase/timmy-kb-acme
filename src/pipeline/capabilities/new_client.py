# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.config_utils import update_config_with_drive_ids
from pipeline.context import ClientContext, validate_slug
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_bytes
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.system_self_check import run_system_self_check
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.workspace_bootstrap import bootstrap_client_workspace
from pipeline.workspace_layout import WorkspaceLayout

ProgressFn = Callable[[int, str], None]

LOGGER = get_structured_logger("pipeline.capabilities.new_client")


def _notify_progress(progress: Optional[ProgressFn], percent: int, message: str) -> None:
    if progress:
        progress(percent, message)


def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": payload.get("action"),
        "status": payload.get("status"),
        "returncode": payload.get("returncode"),
        "errors": list(payload.get("errors", [])) if payload.get("errors") is not None else [],
        "warnings": list(payload.get("warnings", [])) if payload.get("warnings") is not None else [],
        "artifacts": list(payload.get("artifacts", [])) if payload.get("artifacts") is not None else [],
    }


def _run_tool_with_repo_env(
    *,
    repo_root: Path,
    workspace_root: Path,
    run_control_plane_tool: Callable[..., dict[str, Any]],
    tool_module: str,
    slug: str,
    action: str,
    args: list[str] | None = None,
) -> dict[str, Any]:
    prev_repo = os.environ.get("REPO_ROOT_DIR")
    prev_workspace = os.environ.get("WORKSPACE_ROOT_DIR")
    os.environ["REPO_ROOT_DIR"] = str(repo_root)
    os.environ["WORKSPACE_ROOT_DIR"] = str(workspace_root)
    try:
        return run_control_plane_tool(tool_module=tool_module, slug=slug, action=action, args=args)
    finally:
        if prev_repo is None:
            os.environ.pop("REPO_ROOT_DIR", None)
        else:
            os.environ["REPO_ROOT_DIR"] = prev_repo
        if prev_workspace is None:
            os.environ.pop("WORKSPACE_ROOT_DIR", None)
        else:
            os.environ["WORKSPACE_ROOT_DIR"] = prev_workspace


def _vision_pdf_path(layout: WorkspaceLayout) -> Path:
    cfg_dir = layout.config_path.parent
    candidate = layout.vision_pdf or (cfg_dir / "VisionStatement.pdf")
    return ensure_within_and_resolve(layout.repo_root_dir, candidate)


def _workspace_root(repo_root: Path, safe_slug: str) -> Path:
    return ensure_within_and_resolve(
        repo_root,
        repo_root / "output" / f"timmy-kb-{safe_slug}",
    )


def create_new_client_workspace(
    *,
    slug: str,
    client_name: str,
    pdf_bytes: bytes,
    repo_root: Path,
    vision_model: str,
    enable_drive: bool,
    ui_allow_local_only: bool,
    ensure_drive_minimal: Optional[Callable[..., Path]],
    run_control_plane_tool: Callable[..., dict[str, Any]],
    progress: Optional[ProgressFn] = None,
) -> dict[str, Any]:
    safe_slug = validate_slug(slug)
    resolved_name = (client_name or "").strip() or safe_slug
    repo_root_path = repo_root.resolve()
    _notify_progress(progress, 5, "Input cliente validati")

    system_report = run_system_self_check(repo_root_path)
    if not system_report.ok:
        issues = "; ".join(item.message for item in system_report.items if not item.ok)
        raise ConfigError(
            "Self-check di sistema fallito: " + (issues or "problemi sconosciuti"),
            slug=safe_slug,
        )
    _notify_progress(progress, 15, "Self-check ambiente completato")

    workspace_root = _workspace_root(repo_root_path, safe_slug)
    os.environ.setdefault("TIMMY_ALLOW_BOOTSTRAP", "1")

    ctx = ClientContext.load(
        slug=safe_slug,
        require_drive_env=False,
        bootstrap_config=True,
        repo_root_dir=workspace_root,
        logger=LOGGER,
    )
    layout = bootstrap_client_workspace(ctx)
    _notify_progress(progress, 30, "Workspace creato")

    pdf_path = _vision_pdf_path(layout)
    try:
        safe_write_bytes(pdf_path, pdf_bytes, atomic=True)
    except Exception as exc:  # pragma: no cover - I/O dipende dal FS
        raise ConfigError(
            "Impossibile scrivere config/VisionStatement.pdf",
            slug=safe_slug,
            file_path=str(pdf_path),
        ) from exc
    updates = {
        "ai": {"vision": {"vision_statement_pdf": "config/VisionStatement.pdf"}},
        "meta": {"client_name": resolved_name},
    }
    update_config_with_drive_ids(ctx, updates, logger=LOGGER)
    ctx = ClientContext.load(
        slug=safe_slug,
        require_drive_env=False,
        bootstrap_config=False,
        repo_root_dir=layout.repo_root_dir,
        logger=LOGGER,
    )
    layout = WorkspaceLayout.from_context(ctx)
    vision_pdf = _vision_pdf_path(layout)
    _notify_progress(progress, 40, "VisionStatement.pdf salvato e config aggiornato")

    pdf_payload = _run_tool_with_repo_env(
        repo_root=repo_root_path,
        workspace_root=layout.repo_root_dir,
        run_control_plane_tool=run_control_plane_tool,
        tool_module="tools.tuning_pdf_to_yaml",
        slug=safe_slug,
        action="pdf_to_yaml",
        args=["--pdf-path", str(vision_pdf)],
    )["payload"]
    if pdf_payload.get("status") != "ok":
        errors = "; ".join(map(str, pdf_payload.get("errors", [])))
        raise ConfigError(
            "Conversione PDF -> YAML fallita: " + (errors or "errore sconosciuto"),
            slug=safe_slug,
            file_path=str(vision_pdf),
        )
    _notify_progress(progress, 55, "VisionStatement.yaml generato")

    drive_info = {"enabled": False, "skipped_reason": None, "ok": True}
    if ui_allow_local_only:
        drive_info["skipped_reason"] = "local_only"
        _notify_progress(progress, 60, "Drive saltato: modalità local-only")
    elif not enable_drive:
        drive_info["skipped_reason"] = "drive_disabled"
        _notify_progress(progress, 60, "Drive non richiesto")
    else:
        if ensure_drive_minimal is None:
            raise ConfigError(
                "Drive non disponibile: installa gli extra "
                "`pip install .[drive]` o imposta `ui.allow_local_only: true` "
                "per saltare Drive.",
                slug=safe_slug,
            )
        drive_info["enabled"] = True
        _notify_progress(progress, 65, "Provisioning Drive in corso")
        try:
            ensure_drive_minimal(slug=safe_slug, client_name=(resolved_name or None))
            _notify_progress(progress, 70, "Drive pronto (cartelle + config)")
        except Exception as exc:  # pragma: no cover - dipende da Drive/FA
            raise ConfigError(
                "Errore durante il provisioning Drive",
                slug=safe_slug,
            ) from exc
        ctx = ClientContext.load(
            slug=safe_slug,
            require_drive_env=False,
            bootstrap_config=False,
            repo_root_dir=layout.repo_root_dir,
            logger=LOGGER,
        )
        layout = WorkspaceLayout.from_context(ctx)

    vision_yaml_path = vision_yaml_workspace_path(layout.repo_root_dir, pdf_path=vision_pdf)
    _notify_progress(progress, 90, "Workspace locale e VisionStatement YAML pronti")

    return {
        "workspace_root_dir": str(layout.repo_root_dir),
        "config_path": str(layout.config_path),
        "vision_pdf_path": str(vision_pdf),
        "vision_yaml_path": str(vision_yaml_path),
        "semantic_mapping_path": str(layout.mapping_path),
        "drive": drive_info,
        "pdf_to_yaml": {
            "ok": pdf_payload.get("status") == "ok",
            "payload_summary": _summarize_payload(pdf_payload),
        },
    }


def run_vision_provision_for_client(
    *,
    slug: str,
    repo_root: Path,
    vision_model: str,
    run_control_plane_tool: Callable[..., dict[str, Any]],
    progress: Optional[ProgressFn] = None,
) -> dict[str, Any]:
    safe_slug = validate_slug(slug)
    repo_root_path = repo_root.resolve()
    workspace_root = _workspace_root(repo_root_path, safe_slug)
    ctx = ClientContext.load(
        slug=safe_slug,
        require_drive_env=False,
        bootstrap_config=False,
        repo_root_dir=workspace_root,
        logger=LOGGER,
    )
    layout = WorkspaceLayout.from_context(ctx)
    _notify_progress(progress, 70, "Vision (Fase B) in corso")
    vision_payload = _run_tool_with_repo_env(
        repo_root=repo_root_path,
        workspace_root=layout.repo_root_dir,
        run_control_plane_tool=run_control_plane_tool,
        tool_module="tools.tuning_vision_provision",
        slug=safe_slug,
        action="vision_provision",
        args=["--repo-root", str(layout.repo_root_dir), "--model", vision_model],
    )["payload"]
    if vision_payload.get("status") != "ok":
        errors = "; ".join(map(str, vision_payload.get("errors", [])))
        raise ConfigError(
            "Provisioning Vision fallito: " + (errors or "errore sconosciuto"),
            slug=safe_slug,
        )
    layout = WorkspaceLayout.from_context(ctx)
    if not layout.mapping_path.exists():
        raise ConfigError(
            "semantic/semantic_mapping.yaml mancante dopo Vision",
            slug=safe_slug,
            file_path=str(layout.mapping_path),
        )
    _notify_progress(progress, 95, "Vision completata e mapping disponibile")
    return {
        "workspace_root_dir": str(layout.repo_root_dir),
        "semantic_mapping_path": str(layout.mapping_path),
        "vision_payload": vision_payload,
    }
