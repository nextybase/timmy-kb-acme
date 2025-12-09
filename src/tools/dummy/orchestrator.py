# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility di orchestrazione condivise per la dummy KB."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import ensure_within_and_resolve
from semantic.vision_ingest import compile_document_to_vision_yaml

from .bootstrap import build_generic_vision_template_pdf
from .drive import call_drive_build_from_mapping, call_drive_emit_readmes, call_drive_min
from .semantic import (
    ensure_book_skeleton,
    ensure_local_readmes,
    ensure_minimal_tags_db,
    ensure_raw_pdfs,
    load_mapping_categories,
    write_basic_semantic_yaml,
    write_dummy_vision_yaml,
    write_minimal_tags_raw,
)
from .vision import run_vision_with_timeout


def register_client(
    slug: str,
    client_name: str,
    *,
    ClientEntry: Any | None,
    upsert_client: Callable[[Any], Any] | None,
) -> None:
    """Registra il cliente dummy nel registry UI se le API sono disponibili."""
    if not (ClientEntry and callable(upsert_client)):
        return

    try:
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    except Exception:
        timestamp = None

    try:
        entry = ClientEntry(slug=slug, nome=client_name, stato="active", created_at=timestamp, dummy=True)
    except Exception:
        return

    try:
        upsert_client(entry)
    except Exception:
        return


def validate_dummy_structure(base_dir: Path, logger: logging.Logger) -> None:
    """Verifica la presenza dei file fondamentali della dummy KB e solleva se mancano."""
    required_files = [
        ("config", base_dir / "config" / "config.yaml"),
        ("semantic_mapping", base_dir / "semantic" / "semantic_mapping.yaml"),
        ("cartelle_raw", base_dir / "semantic" / "cartelle_raw.yaml"),
        ("tags_db", base_dir / "semantic" / "tags.db"),
        ("book_readme", base_dir / "book" / "README.md"),
        ("book_summary", base_dir / "book" / "SUMMARY.md"),
    ]

    missing: list[dict[str, str]] = []
    for key, path in required_files:
        try:
            safe_path = ensure_within_and_resolve(base_dir, path)
            if not safe_path.exists():
                missing.append({"key": key, "path": str(safe_path)})
        except Exception:
            missing.append({"key": key, "path": str(path)})

    try:
        raw_dir = ensure_within_and_resolve(base_dir, base_dir / "raw")
        has_pdf = any(p.suffix.lower() == ".pdf" for p in raw_dir.rglob("*") if p.is_file())
    except Exception:
        has_pdf = False

    if not has_pdf:
        missing.append({"key": "raw_pdf", "path": str(base_dir / "raw")})

    if missing:
        try:
            logger.error("tools.gen_dummy_kb.validate_structure.missing", extra={"missing": missing})
        except Exception:
            pass
        raise RuntimeError(f"Struttura dummy incompleta: {missing}")


def _count_raw_pdfs(base_dir: Path) -> int:
    try:
        raw_dir = ensure_within_and_resolve(base_dir, base_dir / "raw")
        return sum(1 for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    except Exception:
        return 0


def _count_tags(base_dir: Path) -> int:
    try:
        from storage import tags_store as _tags_store  # type: ignore
    except Exception:
        return 0
    try:
        tags_path = ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags.db")
        payload = _tags_store.load_tags_reviewed(str(tags_path))  # type: ignore[attr-defined]
        tags = payload.get("tags") if isinstance(payload, dict) else []
        return len(tags) if isinstance(tags, list) else 0
    except Exception:
        return 0


def build_dummy_payload(
    *,
    slug: str,
    client_name: str,
    enable_drive: bool,
    enable_vision: bool,
    records_hint: Optional[str],
    logger: logging.Logger,
    repo_root: Path,
    ensure_local_workspace_for_ui: Callable[..., Any],
    run_vision: Callable[..., Any],
    get_env_var: Callable[[str, str | None], str | None],
    ensure_within_and_resolve_fn: Callable[[Path, Path], Path],
    open_for_read_bytes_selfguard: Callable[[Path], Any],
    load_vision_template_sections: Callable[[], Any],
    client_base: Callable[[str], Path],
    pdf_path: Callable[[str], Path],
    register_client_fn: Callable[[str, str], None],
    ClientContext: Any,
    get_client_config: Callable[[Any], Dict[str, Any]] | None,
    ensure_drive_minimal_and_upload_config: Callable[..., Any] | None,
    build_drive_from_mapping: Callable[..., Any] | None,
    emit_readmes_for_raw: Callable[..., Any] | None,
    run_vision_with_timeout_fn: Callable[..., tuple[bool, Optional[dict[str, Any]]]] = run_vision_with_timeout,
    write_basic_semantic_yaml_fn: Callable[..., Dict[str, Any]] = write_basic_semantic_yaml,
    load_mapping_categories_fn: Callable[[Path], Dict[str, Dict[str, Any]]] = load_mapping_categories,
    ensure_minimal_tags_db_fn: Callable[..., Any] = ensure_minimal_tags_db,
    ensure_raw_pdfs_fn: Callable[..., Any] = ensure_raw_pdfs,
    ensure_local_readmes_fn: Callable[..., Any] = ensure_local_readmes,
    ensure_book_skeleton_fn: Callable[[Path], None] = ensure_book_skeleton,
    write_minimal_tags_raw_fn: Callable[[Path], Path] = write_minimal_tags_raw,
    validate_dummy_structure_fn: Callable[[Path, logging.Logger], None] | None = validate_dummy_structure,
    call_drive_min_fn: Callable[..., Optional[dict[str, Any]]] = call_drive_min,
    call_drive_build_from_mapping_fn: Callable[..., Optional[dict[str, Any]]] = call_drive_build_from_mapping,
    call_drive_emit_readmes_fn: Callable[..., Optional[dict[str, Any]]] = call_drive_emit_readmes,
) -> Dict[str, Any]:
    if records_hint:
        try:
            _ = int(records_hint)
        except Exception:
            logger.debug(
                "tools.gen_dummy_kb.records_hint_non_numeric",
                extra={"value": records_hint, "slug": slug},
            )

    repo_pdf = repo_root / "config" / "VisionStatement.pdf"
    if repo_pdf.exists():
        try:
            safe_pdf = ensure_within_and_resolve_fn(repo_root, repo_pdf)
            with open_for_read_bytes_selfguard(safe_pdf) as handle:
                pdf_bytes = handle.read()
        except Exception:
            logger.warning(
                "tools.gen_dummy_kb.vision_template_unreadable",
                extra={"file_path": str(repo_pdf), "slug": slug},
            )
            pdf_bytes = build_generic_vision_template_pdf(load_vision_template_sections)
    else:
        logger.warning(
            "tools.gen_dummy_kb.vision_template_missing",
            extra={"file_path": str(repo_pdf), "slug": slug},
        )
        pdf_bytes = build_generic_vision_template_pdf(load_vision_template_sections)

    ensure_local_workspace_for_ui(slug=slug, client_name=client_name, vision_statement_pdf=pdf_bytes)
    register_client_fn(slug, client_name)

    base_dir = client_base(slug)
    pdf_path_resolved = pdf_path(slug)
    if not pdf_path_resolved.exists():
        try:
            pdf_path_resolved.parent.mkdir(parents=True, exist_ok=True)
            if safe_write_bytes:
                safe_write_bytes(pdf_path_resolved, pdf_bytes, atomic=True)
            else:  # pragma: no cover - fallback
                with pdf_path_resolved.open("wb") as handle:
                    handle.write(pdf_bytes)
        except Exception:
            logger.error(
                "tools.gen_dummy_kb.vision_template_write_failed",
                extra={"slug": slug, "file_path": str(pdf_path_resolved)},
            )
            raise
    yaml_target = ensure_within_and_resolve(base_dir, base_dir / "config" / "visionstatement.yaml")
    try:
        compile_document_to_vision_yaml(pdf_path_resolved, yaml_target)
    except Exception as exc:
        if enable_vision:
            logger.error(
                "tools.gen_dummy_kb.vision_yaml_generation_failed",
                extra={"slug": slug, "error": str(exc), "pdf": str(pdf_path_resolved)},
            )
        else:
            logger.warning(
                "tools.gen_dummy_kb.vision_yaml_generation_skipped",
                extra={"slug": slug, "error": str(exc), "pdf": str(pdf_path_resolved)},
            )
        # Fallback: YAML dummy strutturato per superare il validator
        try:
            yaml_target = write_dummy_vision_yaml(base_dir)
            logger.info(
                "tools.gen_dummy_kb.vision_yaml_dummy_written",
                extra={"slug": slug, "file_path": str(yaml_target)},
            )
        except Exception as inner_exc:  # pragma: no cover - fallback estrema
            logger.error(
                "tools.gen_dummy_kb.vision_yaml_dummy_failed",
                extra={"slug": slug, "error": str(inner_exc)},
            )

    drive_min_info: Dict[str, Any] | None = None
    drive_build_info: Dict[str, Any] | None = None
    drive_readmes_info: Dict[str, Any] | None = None
    categories_for_readmes: Dict[str, Dict[str, Any]] = {}
    fallback_info: Optional[Dict[str, Any]] = None
    vision_completed = False
    vision_status = "error"

    def _apply_semantic_fallback(reason_tag: str) -> None:
        nonlocal fallback_info, categories_for_readmes
        if fallback_info and categories_for_readmes:
            return
        fallback_info = write_basic_semantic_yaml_fn(base_dir, slug=slug, client_name=client_name)
        categories_for_readmes = fallback_info.get("categories", {})
        logger.warning(
            "tools.gen_dummy_kb.vision_fallback_applied",
            extra={"slug": slug, "reason": reason_tag},
        )

    if enable_vision:
        success, vision_meta = run_vision_with_timeout_fn(
            base_dir=base_dir,
            slug=slug,
            pdf_path=pdf_path_resolved,
            timeout_s=120.0,
            logger=logger,
            run_vision=run_vision,
        )
        if success:
            vision_completed = True
            vision_status = "ok"
            categories_for_readmes = load_mapping_categories_fn(base_dir)
        else:
            reason = vision_meta or {}
            message = str(reason.get("error") or "")
            sentinel = str(reason.get("file_path") or "")
            normalized = message.casefold().replace("à", "a")
            if reason.get("reason") == "timeout":
                vision_status = "timeout"
                logger.warning(
                    "tools.gen_dummy_kb.vision_fallback_no_vision",
                    extra={"slug": slug, "mode": "timeout"},
                )
                _apply_semantic_fallback("timeout")
            elif ".vision_hash" in sentinel or "vision gia eseguito" in normalized:
                logger.info(
                    "tools.gen_dummy_kb.vision_already_completed",
                    extra={"slug": slug, "sentinel": sentinel or ".vision_hash"},
                )
                vision_completed = True
                vision_status = "ok"
                categories_for_readmes = load_mapping_categories_fn(base_dir)
            else:
                logger.error(
                    "tools.gen_dummy_kb.vision_fallback_error",
                    extra={
                        "slug": slug,
                        "error": message,
                        "file_path": sentinel or None,
                        "meta": reason or {},
                    },
                )
                _apply_semantic_fallback("error")
    else:
        fallback_info = write_basic_semantic_yaml_fn(base_dir, slug=slug, client_name=client_name)
        categories_for_readmes = fallback_info.get("categories", {})

    try:
        yaml_target = write_dummy_vision_yaml(base_dir)
        logger.info(
            "tools.gen_dummy_kb.vision_dummy_yaml_written",
            extra={"slug": slug, "file_path": str(yaml_target)},
        )
    except Exception as exc:
        logger.warning(
            "tools.gen_dummy_kb.vision_dummy_yaml_failed",
            extra={"slug": slug, "error": str(exc)},
        )

    if not categories_for_readmes:
        categories_for_readmes = load_mapping_categories_fn(base_dir)

    ensure_minimal_tags_db_fn(base_dir, categories_for_readmes, logger=logger)
    ensure_raw_pdfs_fn(base_dir, categories_for_readmes)

    local_readmes = ensure_local_readmes_fn(base_dir, categories_for_readmes)
    ensure_book_skeleton_fn(base_dir)
    try:
        write_minimal_tags_raw_fn(base_dir)
    except Exception as exc:
        logger.warning(
            "tools.gen_dummy_kb.tags_raw_seed_failed",
            extra={"slug": slug, "error": str(exc)},
        )

    if validate_dummy_structure_fn:
        validate_dummy_structure_fn(base_dir, logger)

    if enable_drive:
        try:
            drive_min_info = call_drive_min_fn(
                slug,
                client_name,
                base_dir,
                logger,
                ensure_drive_minimal_and_upload_config,
            )
            drive_build_info = call_drive_build_from_mapping_fn(
                slug,
                client_name,
                base_dir,
                logger,
                build_drive_from_mapping,
            )
            drive_readmes_info = call_drive_emit_readmes_fn(
                slug,
                base_dir,
                logger,
                emit_readmes_for_raw,
            )
        except Exception as exc:
            logger.warning(
                "tools.gen_dummy_kb.drive_provisioning_failed",
                extra={"error": str(exc), "slug": slug},
            )

    fallback_used = bool(fallback_info)

    cfg_out: dict[str, Any] = {}
    if callable(get_client_config) and ClientContext:
        try:
            ctx_cfg = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)  # type: ignore[misc]
            cfg = get_client_config(ctx_cfg) or {}
            cfg_out = {
                "drive_folder_id": cfg.get("drive_folder_id"),
                "drive_raw_folder_id": cfg.get("drive_raw_folder_id"),
            }
        except Exception:
            cfg_out = {}

    health = {
        "vision_status": vision_status,
        "fallback_used": fallback_used,
        "raw_pdf_count": _count_raw_pdfs(base_dir),
        "tags_count": _count_tags(base_dir),
        "mapping_valid": bool(categories_for_readmes),
        "summary_exists": (base_dir / "book" / "SUMMARY.md").exists(),
        "readmes_count": len(local_readmes),
    }

    return {
        "slug": slug,
        "client_name": client_name,
        "paths": {
            "base": str(base_dir),
            "config": str(base_dir / "config" / "config.yaml"),
            "vision_pdf": str(pdf_path_resolved),
            "semantic_mapping": str(base_dir / "semantic" / "semantic_mapping.yaml"),
            "cartelle_raw": str(base_dir / "semantic" / "cartelle_raw.yaml"),
        },
        "drive_min": drive_min_info or {},
        "drive_build": drive_build_info or {},
        "drive_readmes": drive_readmes_info or {},
        "config_ids": cfg_out,
        "vision_used": bool(vision_completed),
        "drive_used": bool(enable_drive),
        "fallback_used": fallback_used,
        "local_readmes": local_readmes,
        "health": health,
    }


__all__ = ["register_client", "validate_dummy_structure", "build_dummy_payload"]
