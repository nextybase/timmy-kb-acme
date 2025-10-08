# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/semantics.py
from __future__ import annotations

import logging
import uuid

import streamlit as st

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.logging_utils import get_structured_logger
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme
from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug

try:
    # disponibilità già usata nel router per compute_sem_enabled
    from ui.utils.workspace import has_raw_pdfs
except Exception:  # pragma: no cover

    def has_raw_pdfs(_slug: str | None) -> tuple[bool, str | None]:
        return False, None


def _make_ctx_and_logger(slug: str) -> tuple[ClientContext, logging.Logger]:
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("ui.semantics", run_id=run_id)
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=run_id)
    return ctx, logger


def _run_convert(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    with st.spinner("Converto PDF in Markdown..."):
        files = convert_markdown(ctx, logger, slug=slug)
    st.success(f"Conversione completata ({len(files)} file di contenuto).")


def _run_enrich(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    base_dir = getattr(ctx, "base_dir", None) or get_paths(slug)["base"]
    vocab = load_reviewed_vocab(base_dir, logger)
    with st.spinner("Arricchisco frontmatter..."):
        touched = enrich_frontmatter(ctx, logger, vocab, slug=slug)
    st.success(f"Frontmatter aggiornato ({len(touched)} file).")


def _run_summary(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    with st.spinner("Genero SUMMARY.md e README.md..."):
        write_summary_and_readme(ctx, logger, slug=slug)
    st.success("SUMMARY.md e README.md generati.")


def _go_preview() -> None:
    # Naviga alla pagina Preview del nuovo router
    try:
        st.query_params["tab"] = "preview"
    except Exception:
        pass
    st.rerun()


# ---------------- UI ----------------

slug = get_slug()
set_slug(slug)

header(slug)
sidebar(slug)

if not slug:
    st.info("Seleziona o inserisci uno slug cliente dalla pagina **Gestisci cliente**.")
    st.stop()

ready, raw_dir = has_raw_pdfs(slug)
if not ready:
    st.info("La semantica sarà disponibile dopo il download dei PDF in `raw/`.")
    st.caption(f"RAW: {raw_dir or 'n/d'}")
    st.stop()

st.subheader("Onboarding semantico")
st.write("Conversione PDF → Markdown, arricchimento del frontmatter e generazione di README/SUMMARY.")

col_a, col_b = st.columns(2)
with col_a:
    if st.button("Converti PDF in Markdown", key="btn_convert", width="stretch"):
        try:
            _run_convert(slug)
        except (ConfigError, ConversionError) as e:
            st.error(str(e))
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella conversione: {e}")
    if st.button("Arricchisci frontmatter", key="btn_enrich", width="stretch"):
        try:
            _run_enrich(slug)
        except (ConfigError, ConversionError) as e:
            st.error(str(e))
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nell'arricchimento: {e}")

with col_b:
    if st.button("Genera README/SUMMARY", key="btn_generate", width="stretch"):
        try:
            _run_summary(slug)
        except (ConfigError, ConversionError) as e:
            st.error(str(e))
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella generazione: {e}")
    # Link “soft” alla pagina Preview del router
    if st.button("Anteprima Docker (HonKit)", key="btn_preview", width="stretch"):
        _go_preview()
