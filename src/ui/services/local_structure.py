# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/services/local_structure.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, sanitize_filename
from pipeline.yaml_utils import yaml_read
from pipeline.logging_utils import get_structured_logger
from ui.utils.context_cache import get_client_context
from pipeline.workspace_layout import WorkspaceLayout

LOGGER = get_structured_logger("ui.services.local_structure")


def _extract_raw_keys(payload: Dict[str, Any]) -> List[str]:
    keys: List[str] = []

    if "raw" in payload:
        raise ConfigError(
            "Schema cartelle_raw.yaml non valido: usa 'folders' con chiavi canoniche (legacy 'raw' non supportato)."
        )

    folders = payload.get("folders")
    if not isinstance(folders, list):
        raise ConfigError("Schema cartelle_raw.yaml non valido: 'folders' mancante o non e' una lista.")
    for item in folders:
        if not isinstance(item, dict):
            raise ConfigError("Schema cartelle_raw.yaml non valido: folders deve contenere oggetti.")
        key = item.get("key") or item.get("name")
        if not key:
            raise ConfigError("Schema cartelle_raw.yaml non valido: ogni folder richiede 'key'.")
        cleaned = sanitize_filename(str(key))
        if cleaned:
            keys.append(cleaned)

    if not keys:
        raise ConfigError("Schema cartelle_raw.yaml non valido: 'folders' non puo' essere vuoto.")

    seen: set[str] = set()
    ordered: List[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def _mkdirs(base_dir: Path, raw_dir: Path, keys: Iterable[str]) -> List[Path]:
    created: List[Path] = []
    safe_raw = ensure_within_and_resolve(base_dir, raw_dir)
    safe_raw.mkdir(parents=True, exist_ok=True)
    for key in keys:
        target = ensure_within_and_resolve(safe_raw, safe_raw / key)
        target.mkdir(parents=True, exist_ok=True)
        created.append(target)
    return created


def materialize_local_raw_from_cartelle(
    slug: str,
    *,
    require_env: bool = False,
) -> Dict[str, Path]:
    """
    Crea raw/<key> leggendo semantic/cartelle_raw.yaml in modo deterministico.
    Non dipende da Drive; fail-fast su YAML non valido o path fuori perimetro.
    """
    ctx = get_client_context(slug, require_env=require_env)
    layout = WorkspaceLayout.from_context(ctx)
    yaml_path = ensure_within_and_resolve(layout.base_dir, layout.semantic_dir / "cartelle_raw.yaml")
    payload = yaml_read(layout.base_dir, yaml_path) or {}
    if not isinstance(payload, dict):
        raise ConfigError("cartelle_raw.yaml non valido: root non e' un oggetto.", slug=slug, file_path=str(yaml_path))
    keys = _extract_raw_keys(payload)
    created = _mkdirs(layout.base_dir, layout.raw_dir, keys)
    LOGGER.info(
        "ui.local_structure.materialized",
        extra={"slug": slug, "count": len(created)},
    )
    return {"raw_dir": layout.raw_dir, "yaml_path": yaml_path}


__all__ = ["materialize_local_raw_from_cartelle"]
