# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility di orchestrazione condivise per la dummy KB."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, Optional

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import ensure_within_and_resolve
from semantic.core import compile_document_to_vision_yaml

from .bootstrap import build_generic_vision_template_pdf, ensure_golden_dummy_pdf
from .drive import call_drive_build_from_mapping, call_drive_emit_readmes, call_drive_min
from .semantic import (
    ensure_book_skeleton,
    ensure_local_readmes,
    ensure_minimal_tags_db,
    ensure_raw_pdfs,
    load_mapping_categories,
    write_basic_semantic_yaml,
    write_minimal_tags_raw,
)
from .vision import run_vision_with_timeout


class HardCheckError(Exception):
    def __init__(self, message: str, health: Dict[str, Any]):
        super().__init__(message)
        self.health = health


def _hardcheck_health(name: str, message: str, latency_ms: int | None = None) -> Dict[str, Any]:
    details: dict[str, Any] = {"ok": False, "details": message}
    if latency_ms is not None:
        details["latency_ms"] = latency_ms
    return {
        "status": "failed",
        "mode": "deep",
        "errors": [message],
        "checks": [name],
        "external_checks": {name: details},
    }


def _resolve_vision_mode(get_env_var: Callable[[str, str | None], str | None]) -> str:
    raw = None
    try:
        raw = get_env_var("VISION_MODE", None)
    except Exception:
        raw = None
    mode = str(raw or "DEEP").strip().lower()
    if mode in {"smoke", "deep"}:
        return mode
    raise ConfigError(f"VISION_MODE non valido: {raw!r}. Usa 'SMOKE' o 'DEEP'.")


def _record_external_check(
    health: Dict[str, Any],
    name: str,
    ok: bool,
    details: str,
    latency_ms: int | None,
) -> None:
    checks = health.setdefault("checks", [])
    if name not in checks:
        checks.append(name)
    external = health.setdefault("external_checks", {})
    entry: dict[str, Any] = {"ok": ok, "details": details}
    if latency_ms is not None:
        entry["latency_ms"] = latency_ms
    external[name] = entry


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
    enable_semantic: bool = True,
    enable_enrichment: bool = True,
    enable_preview: bool = True,
    records_hint: Optional[str],
    deep_testing: bool = False,
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
    load_mapping_categories_fn: Callable[[Path], Dict[str, Dict[str, Any]]] = load_mapping_categories,
    ensure_minimal_tags_db_fn: Callable[..., Any] = ensure_minimal_tags_db,
    ensure_raw_pdfs_fn: Callable[..., Any] = ensure_raw_pdfs,
    ensure_local_readmes_fn: Callable[..., Any] = ensure_local_readmes,
    ensure_book_skeleton_fn: Callable[[Path], None] = ensure_book_skeleton,
    write_basic_semantic_yaml_fn: Callable[..., dict[str, Any]] | None = write_basic_semantic_yaml,
    write_minimal_tags_raw_fn: Callable[[Path], Path] = write_minimal_tags_raw,
    validate_dummy_structure_fn: Callable[[Path, logging.Logger], None] | None = validate_dummy_structure,
    call_drive_min_fn: Callable[..., Optional[dict[str, Any]]] = call_drive_min,
    call_drive_build_from_mapping_fn: Callable[..., Optional[dict[str, Any]]] = call_drive_build_from_mapping,
    call_drive_emit_readmes_fn: Callable[..., Optional[dict[str, Any]]] = call_drive_emit_readmes,
) -> Dict[str, Any]:
    vision_mode = _resolve_vision_mode(get_env_var)
    if vision_mode == "smoke":
        enable_vision = False
        logger.info(
            "tools.gen_dummy_kb.vision_skipped",
            extra={"slug": slug, "mode": "smoke"},
        )
    elif not enable_vision:
        msg = "VISION_MODE=DEEP richiede Vision abilitata"
        logger.error(
            "tools.gen_dummy_kb.vision_required",
            extra={"slug": slug, "mode": "deep"},
        )
        raise HardCheckError(msg, _hardcheck_health("vision_hardcheck", msg))

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
    semantic_dir = base_dir / "semantic"
    sentinel_path = semantic_dir / ".vision_hash"
    mapping_path = semantic_dir / "semantic_mapping.yaml"
    cartelle_path = semantic_dir / "cartelle_raw.yaml"

    categories_for_readmes: Dict[str, Dict[str, Any]] = {}
    vision_completed = False
    vision_status = "skipped" if vision_mode == "smoke" else "error"
    hard_check_results: dict[str, tuple[bool, str, int | None]] = {}

    vision_already_completed = False
    if enable_vision and (sentinel_path.exists() or (mapping_path.exists() and cartelle_path.exists())):
        vision_already_completed = True
        vision_completed = True
        vision_status = "ok"
        categories_for_readmes = load_mapping_categories_fn(base_dir)
        if not categories_for_readmes:
            warn_msg = "Vision marked completed but mapping missing or empty"
            logger.warning(
                "tools.gen_dummy_kb.vision_already_completed_missing_mapping",
                extra={"slug": slug},
            )
            hard_check_results["vision_hardcheck"] = (False, warn_msg, None)
        else:
            hard_check_results["vision_hardcheck"] = (
                True,
                "Vision hard check succeeded (already completed)",
                None,
            )

    pdf_path_resolved = pdf_path(slug)
    if enable_vision and not vision_already_completed and not pdf_path_resolved.exists():
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
    yaml_target: Path | None = None
    if enable_vision and not vision_already_completed:
        yaml_target = ensure_within_and_resolve_fn(base_dir, base_dir / "config" / "visionstatement.yaml")
        if not yaml_target.exists():
            try:
                yaml_target.parent.mkdir(parents=True, exist_ok=True)
                compile_document_to_vision_yaml(pdf_path_resolved, yaml_target)
                logger.info(
                    "tools.gen_dummy_kb.vision_yaml.created",
                    extra={"slug": slug, "path": str(yaml_target)},
                )
            except Exception as exc:
                msg = f"Vision YAML generation failed: {exc}"
                if vision_mode == "deep":
                    logger.error(
                        "tools.gen_dummy_kb.vision_yaml.failed",
                        extra={"slug": slug, "error": str(exc)},
                    )
                    raise HardCheckError(msg, _hardcheck_health("vision_yaml_hardcheck", msg)) from exc
                logger.warning(
                    "tools.gen_dummy_kb.vision_yaml.failed",
                    extra={"slug": slug, "error": str(exc)},
                )
    if deep_testing:
        if not enable_vision:
            msg = "Deep testing requires Vision enabled (secrets/permessi non pronti)"
            logger.error(
                "tools.gen_dummy_kb.vision_hardcheck.disabled",
                extra={"slug": slug, "reason": "vision disabled"},
            )
            raise HardCheckError(msg, _hardcheck_health("vision_hardcheck", msg))
        if not enable_drive:
            msg = "Deep testing requires Drive enabled (secrets/permessi non pronti)"
            logger.error(
                "tools.gen_dummy_kb.drive_hardcheck.disabled",
                extra={"slug": slug, "reason": "drive disabled"},
            )
            raise HardCheckError(msg, _hardcheck_health("drive_hardcheck", msg))
    drive_min_info: Dict[str, Any] | None = None
    drive_build_info: Dict[str, Any] | None = None
    drive_readmes_info: Dict[str, Any] | None = None
    if enable_vision and not vision_already_completed:
        start = perf_counter()
        success, vision_meta = run_vision_with_timeout_fn(
            base_dir=base_dir,
            slug=slug,
            pdf_path=pdf_path_resolved,
            timeout_s=120.0,
            logger=logger,
            run_vision=run_vision,
        )
        latency_ms = int((perf_counter() - start) * 1000)
        if not success:
            reason = vision_meta or {}
            message = str(reason.get("error") or "")
            sentinel = str(reason.get("file_path") or "")
            normalized = message.casefold().replace("اے", "a")
            if ".vision_hash" in sentinel or "vision gia eseguito" in normalized:
                logger.info(
                    "tools.gen_dummy_kb.vision_already_completed",
                    extra={"slug": slug, "sentinel": sentinel or ".vision_hash"},
                )
                vision_already_completed = True
                vision_completed = True
                vision_status = "ok"
                categories_for_readmes = load_mapping_categories_fn(base_dir)
                if not categories_for_readmes:
                    warn_msg = "Vision marked completed but mapping missing or empty"
                    logger.warning(
                        "tools.gen_dummy_kb.vision_already_completed_missing_mapping",
                        extra={"slug": slug},
                    )
                    hard_check_results["vision_hardcheck"] = (False, warn_msg, None)
                else:
                    hard_check_results["vision_hardcheck"] = (
                        True,
                        "Vision hard check succeeded (already completed)",
                        None,
                    )
            else:
                details = message or "Vision run failed"
                if sentinel:
                    details = f"{details} | sentinel={sentinel}"
                err_msg = f"Vision hard check failed; verifica secrets/permessi: {details}"
                logger.error(
                    "tools.gen_dummy_kb.vision_hardcheck.failed",
                    extra={"slug": slug, "error": message, "sentinel": sentinel or None},
                )
                raise HardCheckError(err_msg, _hardcheck_health("vision_hardcheck", err_msg, latency_ms))
        if not vision_already_completed:
            vision_completed = True
            vision_status = "ok"
            categories_for_readmes = load_mapping_categories_fn(base_dir)
            if not categories_for_readmes:
                err_msg = "Vision hard check fallito: nessuna categoria disponibile dopo Vision"
                logger.error(
                    "tools.gen_dummy_kb.vision_hardcheck.failed",
                    extra={"slug": slug, "error": err_msg},
                )
                raise HardCheckError(err_msg, _hardcheck_health("vision_hardcheck", err_msg, latency_ms))
            hard_check_results["vision_hardcheck"] = (
                True,
                "Vision hard check succeeded",
                latency_ms,
            )
            if yaml_target is None:
                yaml_target = ensure_within_and_resolve_fn(base_dir, base_dir / "config" / "visionstatement.yaml")
            if not yaml_target.exists():
                try:
                    compile_document_to_vision_yaml(pdf_path_resolved, yaml_target)
                except Exception as exc:
                    logger.error(
                        "tools.gen_dummy_kb.vision_yaml_generation_failed",
                        extra={"slug": slug, "error": str(exc), "pdf": str(pdf_path_resolved)},
                    )
                    msg = f"Vision YAML generation failed: {exc}"
                    raise HardCheckError(msg, _hardcheck_health("vision_hardcheck", msg)) from exc
    elif not vision_already_completed and enable_semantic:
        categories_for_readmes = load_mapping_categories_fn(base_dir)

    if vision_mode == "smoke" and enable_semantic:
        if write_basic_semantic_yaml_fn and (not mapping_path.exists() or not cartelle_path.exists()):
            try:
                basic_payload = write_basic_semantic_yaml_fn(base_dir, slug=slug, client_name=client_name)
                if not categories_for_readmes and isinstance(basic_payload, dict):
                    basic_categories = basic_payload.get("categories")
                    if isinstance(basic_categories, dict):
                        categories_for_readmes = basic_categories
            except Exception as exc:
                logger.warning(
                    "tools.gen_dummy_kb.semantic_basic_failed",
                    extra={"slug": slug, "error": str(exc)},
                )
        if not categories_for_readmes:
            categories_for_readmes = load_mapping_categories_fn(base_dir)

    local_readmes: list[str] = []
    ensure_book_skeleton_fn(base_dir)
    if enable_semantic:
        if categories_for_readmes:
            ensure_minimal_tags_db_fn(base_dir, categories_for_readmes, logger=logger)
            ensure_raw_pdfs_fn(base_dir, categories_for_readmes)

            local_readmes = ensure_local_readmes_fn(base_dir, categories_for_readmes)
            try:
                write_minimal_tags_raw_fn(base_dir)
            except Exception as exc:
                logger.warning(
                    "tools.gen_dummy_kb.tags_raw_seed_failed",
                    extra={"slug": slug, "error": str(exc)},
                )
        elif vision_mode == "smoke":
            ensure_minimal_tags_db_fn(base_dir, None, logger=logger)
            ensure_raw_pdfs_fn(base_dir, None)

        if vision_mode == "smoke" and validate_dummy_structure_fn:
            validate_dummy_structure_fn(base_dir, logger)
        elif categories_for_readmes and validate_dummy_structure_fn:
            validate_dummy_structure_fn(base_dir, logger)
    else:
        logger.info("tools.gen_dummy_kb.semantic_skipped", extra={"slug": slug})

    if not enable_enrichment:
        logger.info("tools.gen_dummy_kb.enrichment_skipped", extra={"slug": slug})

    if not enable_preview:
        logger.info("tools.gen_dummy_kb.preview_skipped", extra={"slug": slug})

    if enable_drive:
        drive_start = perf_counter()
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
            latency_ms = int((perf_counter() - drive_start) * 1000)
            if deep_testing:
                msg = f"Drive hard check fallito; verifica secrets/permessi/drive ({exc})"
                logger.error(
                    "tools.gen_dummy_kb.drive_hardcheck.failed",
                    extra={"slug": slug, "error": str(exc)},
                )
                raise HardCheckError(msg, _hardcheck_health("drive_hardcheck", msg, latency_ms)) from exc
            logger.warning(
                "tools.gen_dummy_kb.drive_provisioning_failed",
                extra={"error": str(exc), "slug": slug},
            )
        else:
            latency_ms = int((perf_counter() - drive_start) * 1000)
            if deep_testing:
                hard_check_results["drive_hardcheck"] = (
                    True,
                    "Drive hard check succeeded",
                    latency_ms,
                )

    fallback_used = False

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
    health.setdefault("status", "ok")
    health.setdefault("errors", [])
    health.setdefault("checks", [])
    health.setdefault("external_checks", {})
    if deep_testing:
        try:
            golden_path = ensure_golden_dummy_pdf(base_dir)
            with open_for_read_bytes_selfguard(golden_path) as handle:
                golden_bytes = handle.read()
            health.setdefault("checks", []).append("golden_pdf")
            health["golden_pdf"] = {
                "path": str(golden_path),
                "sha256": hashlib.sha256(golden_bytes).hexdigest(),
                "bytes": len(golden_bytes),
            }
        except Exception as exc:
            health["status"] = "failed"
            health.setdefault("errors", []).append(f"Golden PDF generation failed: {exc}")
            logger.error("tools.gen_dummy_kb.golden_pdf.failed", extra={"slug": slug, "error": str(exc)})
            raise RuntimeError(f"Golden PDF generation failed: {exc}") from exc
    health["mode"] = "deep" if deep_testing else "smoke"
    if deep_testing and hard_check_results:
        for name, (ok, details, latency) in hard_check_results.items():
            _record_external_check(health, name, ok, details, latency)

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
