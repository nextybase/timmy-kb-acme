# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Utility di caricamento entità globali da config/entities.yaml."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTITIES_FILE = _REPO_ROOT / "config" / "entities.yaml"


def _entities_path() -> Path:
    """Restituisce il path risolto e validato di config/entities.yaml."""
    try:
        resolved = Path(ensure_within_and_resolve(_REPO_ROOT, _ENTITIES_FILE))
    except Exception as exc:  # pragma: no cover - safety guard
        raise ConfigError("entities.yaml fuori dal workspace consentito.") from exc
    if not resolved.exists():
        raise ConfigError(f"File entities.yaml mancante: {resolved}")
    return resolved


def load_entities() -> Dict[str, Any]:
    """Carica config/entities.yaml e restituisce il mapping completo."""
    path = _entities_path()
    try:
        text = read_text_safe(path.parent, path, encoding="utf-8")
    except Exception as exc:  # pragma: no cover - I/O failure
        raise ConfigError("Impossibile leggere entities.yaml.") from exc

    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ConfigError("entities.yaml deve contenere un mapping YAML valido.")
    return data


def get_all_entities() -> List[Dict[str, Any]]:
    """Restituisce lista piatta di entità con attributi base."""
    data = load_entities()
    categories = data.get("categories") or {}
    if not isinstance(categories, dict):
        return []

    entities: List[Dict[str, Any]] = []
    for category_id, meta in categories.items():
        if not isinstance(meta, dict):
            continue
        items = meta.get("entities") or []
        if not isinstance(items, list):
            continue
        for ent in items:
            if not isinstance(ent, dict):
                continue
            ent_id = str(ent.get("id", "")).strip()
            if not ent_id:
                continue
            entry: Dict[str, Any] = {
                "id": ent_id,
                "label": ent.get("label", ""),
                "category": category_id,
                "document_code": ent.get("document_code", ""),
                "examples": ent.get("examples") or [],
            }
            entities.append(entry)
    return entities


def get_document_code(entity_id: str) -> Optional[str]:
    """Restituisce il prefisso documentale (es. PRJ-) per l'entità richiesta."""
    if not entity_id:
        return None
    normalized = str(entity_id).strip().lower()
    for ent in get_all_entities():
        if str(ent.get("id", "")).strip().lower() == normalized:
            code = ent.get("document_code")
            return str(code) if code is not None else None
    return None
