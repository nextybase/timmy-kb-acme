from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.yaml_utils import clear_yaml_cache
from semantic.api import build_tags_csv
from semantic.tags_io import write_tagging_readme, write_tags_review_stub_from_csv
from storage.tags_store import derive_db_path_from_yaml_path, ensure_schema_v2, load_tags_reviewed
from tag_onboarding import run_nlp_to_db

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

OUTPUT_ROOT = Path(__file__).resolve().parents[3] / "output"


def _require_streamlit() -> None:
    if st is None:
        raise ConfigError("Streamlit non disponibile per l'adapter Estrai Tags.")


def _resolve_paths(ctx: ClientContext, slug: str) -> tuple[Path, Path, Path]:
    base_dir = getattr(ctx, "base_dir", None)
    if base_dir is None:
        base_dir = OUTPUT_ROOT / f"timmy-kb-{slug}"
    base_dir = Path(base_dir).resolve()
    base_dir = ensure_within_and_resolve(base_dir.parent, base_dir)

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
    svc_logger = logger or logging.getLogger("ui.services.tags_adapter")

    try:
        with st.spinner("Preparazione contesto..."):
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            base_dir, raw_dir, semantic_dir = _resolve_paths(ctx, slug)

        yaml_path = ensure_within_and_resolve(base_dir, semantic_dir / "tags_reviewed.yaml")
        db_path = derive_db_path_from_yaml_path(yaml_path)

        nlp_ok = True
        fallback_reason: Optional[str] = None
        with st.spinner("Analisi linguistica dei PDF (NLP)..."):
            try:
                ensure_schema_v2(str(db_path))
                run_nlp_to_db(
                    slug=slug,
                    raw_dir=raw_dir,
                    db_path=db_path,
                    base_dir=base_dir,
                    topn_doc=12,
                    topk_folder=24,
                    rebuild=False,
                    only_missing=False,
                )
            except Exception as exc:
                nlp_ok = False
                fallback_reason = str(exc)
                svc_logger.warning(
                    "ui.tags_adapter.nlp_failed",
                    extra={"slug": slug, "error": fallback_reason},
                )
                st.warning("Analisi NLP non completata: uso fallback euristico.")

        with st.spinner("Generazione tags_raw.csv..."):
            csv_path = build_tags_csv(ctx, svc_logger, slug=slug)
            write_tagging_readme(semantic_dir, svc_logger)
            write_tags_review_stub_from_csv(semantic_dir, csv_path, svc_logger)

        with st.spinner("Aggiornamento YAML tags_reviewed..."):
            data = load_tags_reviewed(db_path)
            yaml_text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            safe_write_text(yaml_path, yaml_text, encoding="utf-8", atomic=True)
            clear_yaml_cache()
            session_key = f"ui.manage.{slug}.tags_reviewed_text"
            if session_key in st.session_state:
                st.session_state[session_key] = yaml_text

        st.success("Estrai Tags completato: tags_reviewed aggiornato.")
        if not nlp_ok and fallback_reason:
            st.info("Pipeline NLP non disponibile: utilizzata generazione euristica (auto-tagger).")
        svc_logger.info(
            "ui.tags_adapter.completed",
            extra={
                "slug": slug,
                "yaml": str(semantic_dir / "tags_reviewed.yaml"),
                "source": "nlp" if nlp_ok else "heuristic",
            },
        )
    except (ConfigError, PipelineError) as exc:
        message = str(exc)
        st.error(f"Estrazione tag non riuscita: {message}")
        svc_logger.error("ui.tags_adapter.failed", extra={"slug": slug, "error": message})
    except Exception:  # pragma: no cover
        st.error("Errore inatteso durante l'estrazione dei tag. Consulta i log.")
        svc_logger.exception("ui.tags_adapter.failed", extra={"slug": slug})


# Alias retro-compatibile
extract_tags_for_review = run_tags_update
