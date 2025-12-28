from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-or-later
"""
Runner headless per Vision: condiviso da CLI e UI.

Responsabilitŕ:
- path-safety e gating hash/sentinel,
- risoluzione config/retention,
- invocazione semantic.vision_provision usando PDF o YAML se giŕ presente.

Nota: non importa moduli UI/Streamlit; utilizzabile in ambienti headless.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, cast

from ai.vision_config import resolve_vision_config, resolve_vision_retention_days
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from semantic.vision_provision import HaltError
from semantic.vision_provision import provision_from_vision_with_config as _provision_from_pdf
from semantic.vision_provision import provision_from_vision_yaml_with_config as _provision_from_yaml

# Alias patchabili per test/dummy
_provision_from_vision_with_config = _provision_from_pdf
_provision_from_vision_yaml_with_config = _provision_from_yaml


def _semantic_dir(base_dir: Path) -> Path:
    sdir = ensure_within_and_resolve(base_dir, base_dir / "semantic")
    return cast(Path, sdir)


def _hash_sentinel(base_dir: Path) -> Path:
    path = ensure_within_and_resolve(_semantic_dir(base_dir), _semantic_dir(base_dir) / ".vision_hash")
    return cast(Path, path)


def _artifacts_paths(base_dir: Path) -> Dict[str, Path]:
    sdir = _semantic_dir(base_dir)
    mapping = ensure_within_and_resolve(sdir, sdir / "semantic_mapping.yaml")
    cartelle = ensure_within_and_resolve(sdir, sdir / "cartelle_raw.yaml")
    return {"mapping": cast(Path, mapping), "cartelle": cast(Path, cartelle)}


def _vision_yaml_path(base_dir: Path, *, pdf_path: Optional[Path] = None) -> Path:
    base = Path(base_dir)
    candidate = (
        (pdf_path.parent / "visionstatement.yaml")
        if pdf_path is not None
        else (base / "config" / "visionstatement.yaml")
    )
    resolved = ensure_within_and_resolve(base, candidate)
    return cast(Path, resolved)


def _sha256_of_file(base_dir: Path, path: Path, chunk_size: int = 8192) -> str:
    safe_path = ensure_within_and_resolve(base_dir, path)
    h = hashlib.sha256()
    with Path(safe_path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_last_hash(base_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Legge il sentinel JSON se presente.
    Ritorna dict con almeno {"hash": str, "model": str, "ts": str} oppure None.
    """
    path = _hash_sentinel(base_dir)
    if not path.exists():
        return None
    try:
        raw = cast(str, read_text_safe(base_dir, path, encoding="utf-8"))
        data = cast(Dict[str, Any], json.loads(raw))
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger = get_structured_logger("pipeline.vision_runner")
        logger.warning(
            "vision_runner.hash_read_failed",
            extra={"path": str(path), "error": str(exc)},
        )
        return None


def _save_hash(base_dir: Path, *, digest: str, model: str) -> None:
    from datetime import datetime, timezone

    payload = json.dumps(
        {"hash": digest, "model": model, "ts": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    safe_write_text(_hash_sentinel(base_dir), payload + "\n")


def run_vision_with_gating(
    ctx: Any,
    logger: logging.Logger,
    *,
    slug: str,
    pdf_path: Path,
    force: bool = False,
    model: Optional[str] = None,
    prepared_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Esegue Vision con gating hash/sentinel condiviso (headless-safe).
    """
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)

    pdf_path = Path(pdf_path)
    safe_pdf = cast(Path, ensure_within_and_resolve(base_dir, pdf_path))
    if not safe_pdf.exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))
    yaml_path = _vision_yaml_path(base_dir, pdf_path=safe_pdf)

    digest = _sha256_of_file(base_dir, safe_pdf)
    last = _load_last_hash(base_dir)
    last_digest = (last or {}).get("hash")

    art = _artifacts_paths(base_dir)
    gate_hit = (last_digest == digest) and art["mapping"].exists() and art["cartelle"].exists()
    logger.info("ui.vision.gate", extra={"slug": slug, "hit": gate_hit})
    if gate_hit and not force:
        raise ConfigError(
            "Vision già eseguito per questo PDF. Usa la modalità 'Forza rigenerazione' per procedere.",
            slug=slug,
            file_path=str(_hash_sentinel(base_dir)),
        )

    resolved_config = resolve_vision_config(ctx, override_model=model)
    retention_days = resolve_vision_retention_days(ctx)

    provision_from_semantic_module = getattr(_provision_from_vision_with_config, "__module__", "").endswith(
        "vision_provision"
    )
    use_yaml = (
        _provision_from_vision_yaml_with_config is not None and provision_from_semantic_module and yaml_path.exists()
    )

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

    _save_hash(base_dir, digest=digest, model=resolved_config.model)
    logger.info("ui.vision.update_hash", extra={"slug": slug, "file_path": str(_hash_sentinel(base_dir))})

    return {
        "skipped": False,
        "hash": digest,
        "mapping": cast(str, result.get("mapping", "")),
        "cartelle_raw": cast(str, result.get("cartelle_raw", "")),
    }


__all__ = ["run_vision_with_gating", "HaltError"]
