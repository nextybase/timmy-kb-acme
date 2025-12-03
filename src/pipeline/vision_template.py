# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except Exception:  # pragma: no cover - PyYAML deve essere disponibile in runtime
    yaml = None  # type: ignore

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

_LOGGER = get_structured_logger("pipeline.vision_template")


def vision_template_path() -> Path:
    """Percorso canonical a config/vision_template.yaml all'interno del repository."""

    repo_root = Path(__file__).resolve().parents[2]
    return Path(ensure_within_and_resolve(repo_root, repo_root / "config" / "vision_template.yaml"))


def load_vision_template_sections() -> List[Dict[str, Any]] | None:
    """
    Carica le sezioni del template Vision se il file esiste e è leggibile.
    In caso di errori torna None (la logica chiamante gestirà il fallback).
    """

    if yaml is None:
        return None
    template_path = vision_template_path()
    if not template_path.exists():
        return None
    try:
        raw = read_text_safe(template_path.parent, template_path, encoding="utf-8")
        payload = yaml.safe_load(raw) or {}
        sections = payload.get("sections")
        if isinstance(sections, list):
            return [section for section in sections if isinstance(section, dict)]
    except Exception:
        _LOGGER.warning("vision_template.load_failed", extra={"file_path": str(template_path)})
    return None
