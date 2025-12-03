# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from kg_builder import build_kg_for_workspace
from pipeline.exceptions import ConfigError, PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from ui.utils.context_cache import get_client_context
from ui.utils.workspace import workspace_root

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


def _require_streamlit() -> None:
    if st is None:
        raise ConfigError("Streamlit non disponibile per il Tag KG Builder.")


def _resolve_workspace(slug: str) -> Path:
    ctx = get_client_context(slug, interactive=False, require_env=False)
    base_dir_obj = getattr(ctx, "base_dir", None)
    if base_dir_obj is None:
        base_dir_obj = workspace_root(slug)
    candidate = Path(base_dir_obj).resolve()
    workspace: Path = ensure_within_and_resolve(candidate.parent, candidate)
    return workspace


def run_tag_kg_builder(
    slug: str,
    *,
    namespace: str | None = None,
    logger: Optional[logging.Logger] = None,
) -> dict[str, Any]:
    """Invoca il Tag KG Builder e ritorna i metadati del grafo generato."""
    _require_streamlit()
    svc_logger = logger or get_structured_logger("ui.services.tag_kg_builder")
    try:
        workspace = _resolve_workspace(slug)
        semantic_dir = ensure_within_and_resolve(workspace, workspace / "semantic")
        tags_raw = ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_raw.json")
        if not tags_raw.exists():
            raise ConfigError("tags_raw.json mancante: genera prima i tag raw.")

        kg: Any = build_kg_for_workspace(workspace, namespace=namespace)
        result: dict[str, int | str] = {
            "namespace": str(getattr(kg, "namespace", namespace or "")),
            "tags": len(getattr(kg, "tags", [])),
            "relations": len(getattr(kg, "relations", [])),
            "json_path": str(ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.json")),
            "md_path": str(ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.md")),
        }
        svc_logger.info(
            "ui.tag_kg_builder.completed",
            extra={
                "slug": slug,
                "namespace": result["namespace"],
                "tag_count": result["tags"],
                "relation_count": result["relations"],
            },
        )
        return result
    except (ConfigError, PipelineError):
        raise
    except Exception as exc:  # pragma: no cover
        svc_logger.exception("ui.tag_kg_builder.failed", extra={"slug": slug, "error": str(exc)})
        raise PipelineError(f"Tag KG Builder fallito: {exc}") from exc
