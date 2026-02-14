from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-or-later
"""
Runner headless per Vision: condiviso da CLI e UI.

Responsabilità:
- path-safety e gating hash/sentinel,
- risoluzione config/retention,
- invocazione semantic.vision_provision usando PDF o YAML se già presente.

Nota: non importa moduli UI/Streamlit; utilizzabile in ambienti headless.
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, cast

from ai.vision_config import resolve_vision_config, resolve_vision_retention_days
from pipeline.beta_flags import is_beta_strict
from pipeline.config_utils import get_client_config, get_drive_id
from pipeline.drive.upload import create_drive_structure_from_names
from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError, WorkspaceLayoutInvalid
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.semantic_mapping_utils import raw_categories_from_semantic_mapping
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.workspace_layout import WorkspaceLayout
from semantic.vision_provision import HaltError
from semantic.vision_provision import provision_from_vision_with_config as _provision_from_pdf
from semantic.vision_provision import provision_from_vision_yaml_with_config as _provision_from_yaml

# Alias patchabili per test/dummy
_provision_from_vision_with_config = _provision_from_pdf
_provision_from_vision_yaml_with_config = _provision_from_yaml


def _resolve_vision_mode(ctx: Any) -> str:
    raw = None
    settings = getattr(ctx, "settings", None)
    try:
        raw = getattr(settings, "vision_mode", None)
    except Exception:
        raw = None
    if not raw:
        raw = get_env_var("VISION_MODE", default="DEEP")
    mode = str(raw or "DEEP").strip().lower()
    if mode == "smoke":
        raise ConfigError(
            "VISION_MODE=SMOKE non supportato in Beta strict-only. Usa 'DEEP'.",
            code="vision.mode.invalid",
            component="vision_runner",
        )
    if mode == "deep":
        return mode
    raise ConfigError(
        f"VISION_MODE non valido: {raw!r}. Usa 'DEEP'.",
        code="vision.mode.invalid",
        component="vision_runner",
    )


def _semantic_dir(repo_root_dir: Path) -> Path:
    sdir = ensure_within_and_resolve(repo_root_dir, repo_root_dir / "semantic")
    return cast(Path, sdir)


def _hash_sentinel(repo_root_dir: Path) -> Path:
    path = ensure_within_and_resolve(_semantic_dir(repo_root_dir), _semantic_dir(repo_root_dir) / ".vision_hash")
    return cast(Path, path)


def _artifacts_paths(repo_root_dir: Path) -> Dict[str, Path]:
    sdir = _semantic_dir(repo_root_dir)
    mapping = ensure_within_and_resolve(sdir, sdir / "semantic_mapping.yaml")
    return {"mapping": cast(Path, mapping)}


def _sha256_of_file(repo_root_dir: Path, path: Path, chunk_size: int = 8192) -> str:
    safe_path = ensure_within_and_resolve(repo_root_dir, path)
    h = hashlib.sha256()
    with Path(safe_path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(value: str) -> str:
    h = hashlib.sha256()
    h.update(value.encode("utf-8"))
    return h.hexdigest()


def _areas_sha256(areas: list[str]) -> str:
    normalized = [a.strip() for a in areas if isinstance(a, str) and a.strip()]
    joined = "\n".join(normalized)
    return _sha256_text(joined)


def _mapping_metrics(repo_root_dir: Path, mapping_path: Path) -> dict[str, Any]:
    safe_mapping = ensure_within_and_resolve(repo_root_dir, mapping_path)
    text = read_text_safe(repo_root_dir, safe_mapping, encoding="utf-8")
    payload = text.encode("utf-8")
    return {
        "mapping_path": str(safe_mapping),
        "mapping_sha256": _sha256_text(text),
        "mapping_size": len(payload),
    }


def _materialize_raw_structure(ctx: Any, logger: logging.Logger, *, repo_root_dir: Path, slug: str) -> Dict[str, Any]:
    layout = WorkspaceLayout.from_workspace(Path(repo_root_dir), slug=slug)
    mapping_path = ensure_within_and_resolve(layout.semantic_dir, layout.semantic_dir / "semantic_mapping.yaml")
    categories = raw_categories_from_semantic_mapping(
        semantic_dir=layout.semantic_dir,
        mapping_path=Path(mapping_path),
    )
    if not categories:
        logger.error(
            "vision_mapping_missing_areas",
            extra={"slug": slug, "path": str(mapping_path), "error": "empty_areas"},
        )
        raise ConfigError(
            f"semantic_mapping.yaml non contiene aree valide: {mapping_path}",
            slug=slug,
            file_path=str(mapping_path),
        )
    areas_hash = _areas_sha256(categories)
    logger.info(
        "raw_structure_areas_extracted",
        extra={"slug": slug, "count": len(categories), "sha256": areas_hash},
    )
    for name in categories:
        target = ensure_within_and_resolve(layout.raw_dir, layout.raw_dir / name)
        target.mkdir(parents=True, exist_ok=True)
    logger.info(
        "raw_structure_local_created",
        extra={"slug": slug, "count": len(categories), "sha256": areas_hash},
    )

    cfg = get_client_config(ctx) or {}
    drive_parent = get_drive_id(cfg, "raw_folder_id")
    if not drive_parent:
        logger.error("raw_structure_drive_missing", extra={"slug": slug, "reason": "drive.raw_folder_id_missing"})
        raise ConfigError(
            "Drive raw folder id mancante: impossibile materializzare raw su Drive.",
            slug=slug,
            file_path=str(mapping_path),
            code="vision.drive.missing",
            component="vision_runner",
        )

    try:
        created = create_drive_structure_from_names(
            ctx=ctx,
            folder_names=categories,
            parent_folder_id=drive_parent,
            log=logger,
        )
    except Exception as exc:
        logger.error(
            "raw_structure_drive_failed",
            extra={"slug": slug, "reason": "drive_error", "error": str(exc)},
        )
        raise ConfigError(
            "Drive non disponibile: impossibile materializzare raw su Drive.",
            slug=slug,
            file_path=str(mapping_path),
            code="vision.drive.unavailable",
            component="vision_runner",
        ) from exc

    logger.info(
        "raw_structure_drive_created",
        extra={"slug": slug, "count": len(created)},
    )
    logger.info(
        "vision.raw_structure.done",
        extra={"local_count": len(categories), "drive_enabled": True, "drive_status": "created"},
    )
    return {
        "areas": categories,
        "areas_sha256": areas_hash,
        "local_count": len(categories),
        "drive_status": "created",
        "drive_reason": "",
        "drive_count": len(created),
    }


def materialize_raw_structure(ctx: Any, logger: logging.Logger, *, repo_root_dir: Path, slug: str) -> Dict[str, Any]:
    """Wrapper pubblico per materializzare la struttura raw/ da semantic_mapping.yaml."""
    return _materialize_raw_structure(ctx, logger, repo_root_dir=repo_root_dir, slug=slug)


def _load_last_hash(repo_root_dir: Path, *, slug: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Legge il sentinel JSON se presente.
    Ritorna dict con almeno {"hash": str, "model": str, "ts": str} oppure None.
    """
    path = _hash_sentinel(repo_root_dir)
    if not path.exists():
        return None
    logger = get_structured_logger("pipeline.vision_runner")

    def _invalid(reason: str) -> Dict[str, Any]:
        logger.warning(
            "vision.hash_sentinel_invalid",
            extra={"slug": slug, "file_path": str(path), "reason": reason},
        )
        # Sentinel invalido => forza rerun deterministico (hash mismatch)
        return {}

    try:
        raw = cast(str, read_text_safe(repo_root_dir, path, encoding="utf-8"))
        data = cast(Dict[str, Any], json.loads(raw))
        if not isinstance(data, dict):
            return _invalid("json_not_object")
        digest = data.get("hash")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return _invalid("invalid_hash_format")
        return data
    except Exception as exc:
        return _invalid(f"{type(exc).__name__}: {exc}")


def _save_hash(repo_root_dir: Path, *, digest: str, model: str) -> None:
    from datetime import datetime, timezone

    payload = json.dumps(
        {"hash": digest, "model": model, "ts": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    safe_write_text(_hash_sentinel(repo_root_dir), payload + "\n")


def run_vision_with_gating(
    ctx: Any,
    logger: logging.Logger,
    *,
    slug: str,
    pdf_path: Path,
    model: Optional[str] = None,
    prepared_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Esegue Vision con gating hash/sentinel condiviso (headless-safe).
    """
    _resolve_vision_mode(ctx)

    try:
        repo_root_dir = Path(ctx.repo_root_dir_required())
    except AttributeError as exc:
        raise ConfigError("Context privo di repo_root_dir_required per Vision onboarding.", slug=slug) from exc
    layout = WorkspaceLayout.from_context(cast(Any, ctx))
    pdf_path = Path(pdf_path)
    safe_pdf = cast(Path, ensure_within_and_resolve(repo_root_dir, pdf_path))
    if not safe_pdf.exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))
    yaml_path = vision_yaml_workspace_path(Path(repo_root_dir), pdf_path=safe_pdf)

    digest = _sha256_of_file(repo_root_dir, safe_pdf)
    resolved_config = resolve_vision_config(ctx, override_model=model)
    retention_days = resolve_vision_retention_days(ctx)
    last = _load_last_hash(repo_root_dir, slug=slug)
    last_digest = (last or {}).get("hash")
    last_model = (last or {}).get("model")
    strict_mode = is_beta_strict()

    phase_b_ready = True
    phase_b_reason = "ready"
    try:
        layout.require_phase_b_assets()
    except WorkspaceLayoutInvalid:
        phase_b_ready = False
        phase_b_reason = "phase_b_not_ready"

    model_missing = last is not None and not isinstance(last_model, str)
    model_match = isinstance(last_model, str) and (last_model == resolved_config.model)
    gate_hit = (last_digest == digest) and model_match and phase_b_ready
    if gate_hit:
        gate_reason = "hash+model"
    elif not phase_b_ready:
        gate_reason = phase_b_reason
    elif last is None:
        gate_reason = "sentinel_missing"
    elif last_digest != digest:
        gate_reason = "hash_miss"
    elif model_missing:
        gate_reason = "model_missing_strict" if strict_mode else "model_missing_non_strict"
    else:
        gate_reason = "model_miss"
    logger.info("ui.vision.gate", extra={"slug": slug, "hit": gate_hit, "reason": gate_reason})
    if gate_hit:
        layout.require_phase_b_assets()
        try:
            metrics = _mapping_metrics(Path(repo_root_dir), layout.mapping_path)
        except (ConfigError, OSError, ValueError, UnicodeError) as exc:
            raise ConfigError(
                f"semantic_mapping.yaml non leggibile: {exc}",
                slug=slug,
                file_path=str(layout.mapping_path),
            ) from exc
        logger.info("vision_completed", extra={"slug": slug, **metrics})
        raw_info = _materialize_raw_structure(ctx, logger, repo_root_dir=Path(repo_root_dir), slug=slug)
        return {
            "skipped": True,
            "hash": digest,
            "mapping": str(layout.mapping_path),
            "raw_structure": raw_info,
        }

    use_yaml = _provision_from_vision_yaml_with_config is not None and yaml_path.exists()

    try:
        if use_yaml:
            result = _provision_from_vision_yaml_with_config(
                ctx=ctx,
                logger=logger,
                slug=slug,
                yaml_path=yaml_path,
                config=resolved_config,
                retention_days=retention_days,
                prepared_prompt=prepared_prompt,
            )
        else:
            result = _provision_from_vision_with_config(
                ctx=ctx,
                logger=logger,
                slug=slug,
                pdf_path=safe_pdf,
                config=resolved_config,
                retention_days=retention_days,
                prepared_prompt=prepared_prompt,
            )
    except HaltError:
        raise

    layout.require_phase_b_assets()

    try:
        metrics = _mapping_metrics(Path(repo_root_dir), _artifacts_paths(repo_root_dir)["mapping"])
    except Exception as exc:
        raise ConfigError(
            f"semantic_mapping.yaml non leggibile: {exc}",
            slug=slug,
            file_path=str(_artifacts_paths(repo_root_dir)["mapping"]),
        ) from exc
    logger.info("vision_completed", extra={"slug": slug, **metrics})

    raw_info = _materialize_raw_structure(ctx, logger, repo_root_dir=Path(repo_root_dir), slug=slug)

    _save_hash(repo_root_dir, digest=digest, model=resolved_config.model)
    logger.info("ui.vision.update_hash", extra={"slug": slug, "file_path": str(_hash_sentinel(repo_root_dir))})

    return {
        "skipped": False,
        "hash": digest,
        "mapping": cast(str, result.get("mapping", "")),
        "raw_structure": raw_info,
    }


__all__ = ["run_vision_with_gating", "HaltError", "materialize_raw_structure"]
