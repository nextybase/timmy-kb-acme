# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.yaml_utils import clear_yaml_cache
from semantic.api import build_tags_csv
from semantic.tags_io import write_tagging_readme, write_tags_review_stub_from_csv
from ui.utils.context_cache import get_client_context
from ui.utils.workspace import workspace_root

if TYPE_CHECKING:  # pragma: no cover
    from pipeline.context import ClientContext
else:  # pragma: no cover
    from typing import Any

    ClientContext = Any  # type: ignore[misc]

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


def _require_streamlit() -> None:
    if st is None:
        raise ConfigError("Streamlit non disponibile per l'adapter Estrai Tags.")


def _resolve_paths(ctx: ClientContext, slug: str) -> tuple[Path, Path, Path]:
    base_dir = getattr(ctx, "base_dir", None)
    if base_dir is None:
        base_dir = workspace_root(slug)
    else:
        candidate = Path(base_dir)
        base_dir = ensure_within_and_resolve(candidate.parent, candidate)

    raw_dir = getattr(ctx, "raw_dir", None) or (base_dir / "raw")
    raw_dir = ensure_within_and_resolve(base_dir, Path(raw_dir))
    raw_dir.mkdir(parents=True, exist_ok=True)

    semantic_dir = getattr(ctx, "semantic_dir", None) or (base_dir / "semantic")
    semantic_dir = ensure_within_and_resolve(base_dir, Path(semantic_dir))
    semantic_dir.mkdir(parents=True, exist_ok=True)

    return base_dir, raw_dir, semantic_dir


def run_tags_update(slug: str, logger: Optional[logging.Logger] = None) -> None:
    """Genera/aggiorna tags_reviewed in-process mostrando l'avanzamento nella UI."""
    _require_streamlit()
    svc_logger = logger or get_structured_logger("ui.services.tags_adapter")

    try:
        with st.spinner("Preparazione contesto..."):
            ctx = get_client_context(slug, interactive=False, require_env=False)
            base_dir, raw_dir, semantic_dir = _resolve_paths(ctx, slug)

        with st.spinner("Generazione tags_raw.csv (SpaCy/euristica)..."):
            csv_path = build_tags_csv(ctx, svc_logger, slug=slug)
            write_tagging_readme(semantic_dir, svc_logger)
            write_tags_review_stub_from_csv(semantic_dir, csv_path, svc_logger)

        # Niente scrittura automatica dello YAML: l'utente pubblica esplicitamente dalla UI.
        clear_yaml_cache()
        st.success("Estrai Tags completato (SpaCy/euristica). Usa 'Pubblica tag revisionati' per generare lo YAML.")
        backend = os.getenv("TAGS_NLP_BACKEND", "spacy").strip().lower() or "spacy"
        entities_written = getattr(ctx, "last_entities_written", None)
        svc_logger.info(
            "ui.tags_adapter.completed",
            extra={
                "slug": slug,
                "yaml": str(semantic_dir / "tags_reviewed.yaml"),
                "source": backend,
                "entities_written": entities_written,
            },
        )
    except (ConfigError, PipelineError) as exc:
        message = str(exc)
        st.error(f"Estrazione tag non riuscita: {message}")
        svc_logger.error("ui.tags_adapter.failed", extra={"slug": slug, "error": message})
    except Exception:  # pragma: no cover
        st.error("Errore inatteso durante l'estrazione dei tag. Consulta i log.")
        svc_logger.exception("ui.tags_adapter.failed", extra={"slug": slug})
