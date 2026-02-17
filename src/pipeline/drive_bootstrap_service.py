# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from pipeline.config_utils import get_client_config, update_config_with_drive_ids, write_client_config_file
from pipeline.context import ClientContext
from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import (
    get_structured_logger,
    mask_id_map,
    mask_partial,
    mask_updates,
    phase_scope,
    tail_path,
)
from pipeline.observability_config import get_observability_settings
from pipeline.path_utils import ensure_valid_slug, ensure_within
from pipeline.types import WorkflowResult
from pipeline.workspace_bootstrap import bootstrap_client_workspace
from pipeline.workspace_layout import WorkspaceLayout


def _sync_env(context: ClientContext, *, require_env: bool) -> None:
    """Allinea nel `context.env` le variabili critiche lette da os.environ."""
    for key in ("SERVICE_ACCOUNT_FILE", "DRIVE_ID"):
        if not context.env.get(key):
            val = get_env_var(key, required=require_env)
            if val:
                context.env[key] = val


def prepare_context_and_logger(
    slug: str,
    *,
    interactive: bool,
    require_drive_env: bool = False,
    run_id: Optional[str],
    client_name: Optional[str],
    prompt,
    bootstrap_workspace_fn: Callable[[ClientContext], Any] = bootstrap_client_workspace,
) -> Tuple[ClientContext, logging.Logger, str]:
    """Prepara `ClientContext` e logger strutturato per il pre-onboarding."""
    obs_settings = get_observability_settings()
    obs_kwargs = {
        "level": obs_settings.log_level,
        "redact_logs": obs_settings.redact_logs,
        "enable_tracing": obs_settings.tracing_enabled,
    }

    early_logger = get_structured_logger("pre_onboarding", run_id=run_id, **obs_kwargs)
    slug = ensure_valid_slug(slug, interactive=interactive, prompt=prompt, logger=early_logger)

    if client_name is None and interactive:
        client_name = prompt("Inserisci nome cliente: ").strip()
    if not client_name:
        client_name = slug

    os.environ.setdefault("TIMMY_ALLOW_BOOTSTRAP", "1")

    context: ClientContext = ClientContext.load(
        slug=slug,
        require_drive_env=require_drive_env,
        run_id=run_id,
        bootstrap_config=True,
    )

    bootstrap_workspace_fn(context)
    layout = WorkspaceLayout.from_context(context)
    layout.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = layout.log_file

    logger = get_structured_logger(
        "pre_onboarding",
        log_file=log_file,
        context=context,
        run_id=run_id,
        **obs_kwargs,
    )
    logger.info("cli.pre_onboarding.config_loaded", extra={"slug": context.slug, "path": str(layout.config_path)})
    logger.info("cli.pre_onboarding.started", extra={"slug": context.slug})
    return context, logger, client_name


def create_local_structure(
    context: ClientContext,
    logger: logging.Logger,
    *,
    client_name: str,
    bootstrap_workspace_fn: Callable[[ClientContext], Any] = bootstrap_client_workspace,
) -> Path:
    """Crea raw/, book/, config/ e scrive config.yaml minimale. Restituisce il path di config."""
    bootstrap_workspace_fn(context)
    layout = WorkspaceLayout.from_context(context)
    cfg_path = layout.config_path
    repo_root_dir = layout.repo_root_dir

    cfg: Dict[str, Any] = {}
    try:
        cfg = get_client_config(context) or {}
    except ConfigError:
        cfg = {}
    if client_name:
        meta_section = cfg.get("meta")
        if not isinstance(meta_section, dict):
            meta_section = {}
            cfg["meta"] = meta_section
        if not meta_section.get("client_name"):
            meta_section["client_name"] = client_name

    write_client_config_file(context, cfg)

    ensure_within(repo_root_dir, layout.raw_dir)
    ensure_within(repo_root_dir, layout.book_dir)
    ensure_within(repo_root_dir, cfg_path.parent)

    cfg_dir = cfg_path.parent
    cfg_dir.mkdir(parents=True, exist_ok=True)

    with phase_scope(logger, stage="create_local_structure", customer=context.slug) as m:
        try:
            base = repo_root_dir
            count = sum(1 for p in (base.iterdir() if base else []) if p.is_dir()) if base else None
            m.set_artifacts(count)
        except Exception:
            m.set_artifacts(None)

    logger.info(
        "cli.pre_onboarding.local_skeleton.created",
        extra={
            "raw": str(layout.raw_dir),
            "book": str(layout.book_dir),
            "config": str(cfg_path.parent),
        },
    )

    return cfg_path


def drive_phase(
    context: ClientContext,
    logger: logging.Logger,
    *,
    config_path: Path,
    client_name: str,
    require_env: bool,
) -> WorkflowResult:
    """Crea struttura remota minima su Drive, carica config e aggiorna il config locale."""
    _sync_env(context, require_env=require_env)
    logger.info(
        "cli.pre_onboarding.drive.preflight",
        extra={
            "SERVICE_ACCOUNT_FILE": mask_partial(context.env.get("SERVICE_ACCOUNT_FILE")),
            "DRIVE_ID": mask_partial(context.env.get("DRIVE_ID")),
        },
    )
    from pipeline.drive_utils import (
        create_drive_folder,
        create_drive_minimal_structure,
        get_drive_service,
        upload_config_to_drive_folder,
    )

    service = get_drive_service(context)

    drive_parent_id = context.env.get("DRIVE_ID")
    if not drive_parent_id:
        raise ConfigError("DRIVE_ID non impostato nell'ambiente (.env).")

    redact = bool(getattr(context, "redact_logs", False))
    logger.info(
        "cli.pre_onboarding.drive.start",
        extra={"slug": context.slug, "parent": mask_partial(drive_parent_id)},
    )

    with phase_scope(logger, stage="drive_create_client_folder", customer=context.slug) as m:
        client_folder_id = create_drive_folder(service, context.slug, parent_id=drive_parent_id, redact_logs=redact)
        m.set_artifacts(1)
    logger.info(
        "cli.pre_onboarding.drive.folder_created",
        extra={"client_folder_id": mask_partial(client_folder_id)},
    )

    with phase_scope(logger, stage="drive_create_structure_minimal", customer=context.slug) as m:
        created_map = create_drive_minimal_structure(service, client_folder_id, redact_logs=redact)
        try:
            m.set_artifacts(len(created_map or {}))
        except Exception:
            m.set_artifacts(None)
    logger.info(
        "cli.pre_onboarding.drive.structure_created",
        extra={
            "config_tail": tail_path(config_path),
            "created_map_masked": mask_id_map(created_map),
        },
    )

    raw_folder_id = created_map.get("raw")
    if not raw_folder_id:
        raise ConfigError(
            f"Cartella RAW non trovata su Drive per slug '{context.slug}'.",
            drive_id=client_folder_id,
            slug=context.slug,
        )
    contrattualistica_folder_id = created_map.get("contrattualistica")
    if not contrattualistica_folder_id:
        raise ConfigError(
            f"Cartella contrattualistica non trovata su Drive per slug '{context.slug}'.",
            drive_id=client_folder_id,
            slug=context.slug,
        )

    with phase_scope(logger, stage="drive_upload_config", customer=context.slug) as m:
        uploaded_cfg_id = upload_config_to_drive_folder(
            service, context, parent_id=client_folder_id, redact_logs=redact
        )
        m.set_artifacts(1)
    logger.info(
        "cli.pre_onboarding.drive_config_uploaded",
        extra={"slug": context.slug, "uploaded_cfg_id": mask_partial(uploaded_cfg_id)},
    )

    updates = {
        "integrations": {
            "drive": {
                "folder_id": client_folder_id,
                "raw_folder_id": raw_folder_id,
                "contrattualistica_folder_id": contrattualistica_folder_id,
                "config_folder_id": client_folder_id,
            }
        },
    }
    if client_name:
        updates["meta"] = {"client_name": client_name}
    update_config_with_drive_ids(context, updates=updates, logger=logger)
    logger.info(
        "cli.pre_onboarding.config_updated_with_drive_ids",
        extra={"slug": context.slug, "updates_masked": mask_updates(updates)},
    )
    return {
        "ok": True,
        "message": "cli.pre_onboarding.drive_phase_completed",
        "details": {"slug": context.slug, "stage": "drive_phase"},
    }
