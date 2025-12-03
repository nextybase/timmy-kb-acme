# SPDX-License-Identifier: GPL-3.0-only
"""
Tiny helper per tracciare lo stato del wizard semantico.

Lo stato è persistito per slug sotto `clients_db/semantic_progress/<slug>.json`
usando scritture atomiche e path-safety.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from pipeline.context import validate_slug
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG = get_structured_logger("ui.semantic_progress")

SEMANTIC_STEP_IDS = ("convert", "enrich", "summary", "preview")
STEP_CONVERT, STEP_ENRICH, STEP_SUMMARY, STEP_PREVIEW = SEMANTIC_STEP_IDS


def _normalize_slug(slug: str) -> str:
    value = slug.strip().lower()
    if not value:
        raise ConfigError("Slug non può essere vuoto", slug=slug)
    validate_slug(value)
    return value


def _get_storage_dir() -> Path:
    """Restituisce la directory di storage assicurandone l'esistenza."""

    storage_dir: Path = ensure_within_and_resolve(REPO_ROOT, REPO_ROOT / "clients_db" / "semantic_progress")
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def _progress_path(slug: str) -> Path:
    normalized = _normalize_slug(slug)
    storage_dir = _get_storage_dir()
    progress_path: Path = ensure_within_and_resolve(REPO_ROOT, storage_dir / f"{normalized}.json")
    return progress_path


def _read_progress(path: Path) -> Dict[str, bool]:
    try:
        raw = read_text_safe(path.parent, path, encoding="utf-8")
    except Exception:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        _LOG.warning("ui.semantic_progress.read_invalid", extra={"path": str(path)})
        return {}
    if not isinstance(payload, dict):
        return {}
    result: Dict[str, bool] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        result[key] = bool(value)
    return result


def _write_progress(path: Path, data: Dict[str, bool]) -> None:
    try:
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        safe_write_text(path, payload + "\n", encoding="utf-8", atomic=True)
    except Exception as exc:
        _LOG.warning("ui.semantic_progress.write_failed", extra={"path": str(path), "error": str(exc)})


def get_semantic_progress(slug: str) -> Dict[str, bool]:
    """Restituisce lo stato dei passi semantici per lo slug richiesto."""
    path = _progress_path(slug)
    stored = _read_progress(path)
    return {step: stored.get(step, False) for step in SEMANTIC_STEP_IDS}


def mark_semantic_step_done(slug: str, step_id: str) -> None:
    """Segna un passo semantico come completato per lo slug dato."""
    if step_id not in SEMANTIC_STEP_IDS:
        raise ConfigError(f"Step non valido: {step_id!r}", slug=slug)
    path = _progress_path(slug)
    progress = _read_progress(path)
    progress[step_id] = True
    _write_progress(path, progress)
