# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.config_utils import merge_client_config_from_template, update_config_with_drive_ids
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_bytes, safe_write_text
from pipeline.path_utils import ensure_within, read_text_safe
from pipeline.workspace_layout import WorkspaceLayout

from pipeline.drive_bootstrap_service import create_local_structure, prepare_context_and_logger


def ensure_local_workspace_for_ui(
    slug: str,
    client_name: Optional[str] = None,
    vision_statement_pdf: Optional[bytes] = None,
    *,
    prompt,
    get_env_var_fn,
    get_client_config_fn,
    merge_client_config_from_template_fn: Callable[..., Any] = merge_client_config_from_template,
    bootstrap_workspace_fn=None,
) -> Path:
    """Garantisce la presenza del workspace locale del cliente per la UI."""
    context, logger, resolved_name = prepare_context_and_logger(
        slug,
        interactive=False,
        require_drive_env=False,
        run_id=None,
        client_name=client_name,
        prompt=prompt,
        bootstrap_workspace_fn=bootstrap_workspace_fn,
    )

    config_path = create_local_structure(
        context,
        logger,
        client_name=(resolved_name or slug),
        bootstrap_workspace_fn=bootstrap_workspace_fn,
    )
    layout = WorkspaceLayout.from_context(context)

    if vision_statement_pdf:
        repo_root_dir = layout.repo_root_dir
        cfg_dir = layout.config_path.parent
        target = layout.vision_pdf
        cfg_dir.mkdir(parents=True, exist_ok=True)
        ensure_within(repo_root_dir, target)
        safe_write_bytes(target, vision_statement_pdf, atomic=True)
        logger.info(
            "vision_statement_saved",
            extra={
                "slug": context.slug,
                "file_path": str(target),
                "context_repo_root_dir": str(repo_root_dir),
                "repo_root_dir": str(context.repo_root_dir or "<none>"),
            },
        )

        updates: dict[str, Any] = {"ai": {"vision": {"vision_statement_pdf": "config/VisionStatement.pdf"}}}
        if resolved_name:
            updates["meta"] = {"client_name": resolved_name}
        update_config_with_drive_ids(context, updates, logger=logger)

    try:
        template_root = get_env_var_fn("TEMPLATE_CONFIG_ROOT", required=False)
        if template_root:
            template_cfg = Path(template_root).expanduser().resolve() / "config" / "config.yaml"
        else:
            repo_root = Path(__file__).resolve().parents[1]
            template_cfg = repo_root / "config" / "config.yaml"

        if template_cfg.exists():
            merge_client_config_from_template_fn(context, template_cfg)
            logger.info(
                "cli.pre_onboarding.config_merged_from_template",
                extra={"slug": context.slug, "file_path": str(template_cfg)},
            )
    except ConfigError:
        raise
    except Exception as exc:
        logger.warning(
            "cli.pre_onboarding.config_merge_failed",
            extra={"slug": context.slug, "err": str(exc).splitlines()[:1]},
        )
        raise ConfigError(
            "Merge del template config.yaml fallito durante il bootstrap UI.",
            slug=context.slug,
            file_path=str(template_cfg) if "template_cfg" in locals() else None,
        ) from exc

    prompt_dest = layout.config_path.parent / "assistant_vision_system_prompt.txt"
    try:
        repo_root = Path(__file__).resolve().parents[1]
        prompt_src = repo_root / "config" / "assistant_vision_system_prompt.txt"
        if not prompt_src.exists():
            raise ConfigError(
                "System prompt Vision mancante: allinea config/assistant_vision_system_prompt.txt.",
                slug=context.slug,
                file_path=str(prompt_src),
                code="vision.prompt.missing",
            )
        prompt_dest.parent.mkdir(parents=True, exist_ok=True)
        ensure_within(layout.repo_root_dir, prompt_dest)
        source_text = read_text_safe(prompt_src.parent, prompt_src, encoding="utf-8")
        safe_write_text(prompt_dest, source_text, encoding="utf-8", atomic=True)
    except ConfigError:
        raise
    except Exception as exc:
        logger.error(
            "cli.pre_onboarding.prompt_copy_failed",
            extra={"slug": context.slug, "error": str(exc)},
        )
        raise ConfigError(
            "Copia del system prompt Vision fallita.",
            slug=context.slug,
            file_path=str(prompt_dest),
            code="vision.prompt.write_failed",
        ) from exc

    _validate_vision_artifacts(context, layout, get_client_config_fn=get_client_config_fn)

    logger.info(
        "cli.pre_onboarding.workspace.created",
        extra={
            "slug": context.slug,
            "base": str(layout.repo_root_dir),
            "config": str(config_path),
        },
    )
    return config_path


def _resolve_vision_pdf_path(repo_root: Path, candidate: str | Path) -> Path:
    target = Path(candidate)
    if not target.is_absolute():
        target = repo_root / target
    from pipeline.path_utils import ensure_within_and_resolve

    return ensure_within_and_resolve(repo_root, target)


def _hash_file_sha256(path: Path) -> str:
    import hashlib

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _validate_vision_artifacts(
    context,
    layout: WorkspaceLayout,
    *,
    get_client_config_fn,
) -> list[str]:
    repo_root = layout.repo_root_dir
    if repo_root is None:
        return []

    config = get_client_config_fn(context) or {}
    vision_cfg = config.get("ai", {}).get("vision")
    if not (isinstance(vision_cfg, dict) and vision_cfg.get("vision_statement_pdf")):
        return []

    pdf_path = _resolve_vision_pdf_path(repo_root, vision_cfg["vision_statement_pdf"])
    if not pdf_path.exists() or not pdf_path.is_file():
        raise ConfigError(
            "VisionStatement.pdf mancante o non leggibile nel workspace.",
            slug=context.slug,
            file_path=str(pdf_path),
            code="vision.artifact.missing",
        )

    prompt_path = layout.config_path.parent / "assistant_vision_system_prompt.txt"
    if not prompt_path.exists() or not prompt_path.is_file():
        raise ConfigError(
            "System prompt Vision mancante nel workspace.",
            slug=context.slug,
            file_path=str(prompt_path),
            code="vision.prompt.missing",
        )

    return [
        f"vision_pdf_sha256:{_hash_file_sha256(pdf_path)}",
        f"vision_prompt_sha256:{_hash_file_sha256(prompt_path)}",
    ]
