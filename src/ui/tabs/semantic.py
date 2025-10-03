from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from pipeline.context import ClientContext
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme
from ui.clients_store import get_state, set_state


def render_semantic_tab(*, log: Any, slug: str) -> None:
    """Render the Semantic tab: conversion, enrichment, summary/readme.
    UI-only layer: does not alter business logic or public APIs.
    """
    st.subheader("Semantica — conversione e arricchimento")
    st.caption(
        "Disponibile quando lo stato cliente è almeno **pronto** (dopo download dei PDF in `raw/`). "
        "Sequenza consigliata: 1) Converti → 2) Arricchisci → 3) SUMMARY & README."
    )

    # Gating sull'abilitazione della sezione in base allo stato cliente
    try:
        state = (get_state(slug) or "").strip().lower()
    except Exception:
        state = ""  # fallback prudente: meglio mostrare il warning che bloccare la UI

    if state not in {"pronto", "arricchito", "finito"}:
        st.warning("Semantica disponibile dopo il completamento del flusso Drive.")
        with st.expander("Requisiti per proseguire", expanded=False):
            st.markdown("- PDF scaricati in `raw/` tramite tab Drive.")
            st.markdown("- README generati in `raw/` (step 2).")
            st.markdown("- Stato cliente aggiornato almeno a `pronto`.")
        return

    # 1) Conversione RAW -> BOOK (Markdown)
    if st.button(
        "1) Converti PDF in Markdown",
        key="btn_sem_convert",
        use_container_width=True,
        help="Converte i PDF presenti in `raw/` in file Markdown sotto `book/`. Operazione idempotente.",
    ):
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            convert_markdown(ctx, log, slug=slug)
            st.success("Conversione completata.")
        except Exception as e:
            st.exception(e)

    # 2) Arricchimento frontmatter
    if st.button(
        "2) Arricchisci frontmatter",
        key="btn_sem_enrich",
        use_container_width=True,
        help="Applica vocabolario revisionato e metadati ai Markdown in `book/`.",
    ):
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            paths = get_paths(slug)
            base_dir: Path = ctx.base_dir or paths["base"]
            vocab = load_reviewed_vocab(base_dir, log)
            touched = enrich_frontmatter(ctx, log, vocab, slug=slug)
            st.success(f"Frontmatter arricchiti: {len(touched)}")
            # Allineamento stato come da flusso esistente
            set_state(slug, "arricchito")
        except Exception as e:
            st.exception(e)

    # 3) Generazione SUMMARY.md e README.md
    if st.button(
        "3) Genera SUMMARY e README",
        key="btn_sem_md",
        use_container_width=True,
        help="Costruisce/valida `SUMMARY.md` e `README.md` nella cartella `book/`.",
    ):
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            write_summary_and_readme(ctx, log, slug=slug)
            st.success("`SUMMARY.md` e `README.md` generati/validati.")
            # Allineamento stato come da flusso esistente
            set_state(slug, "finito")
        except Exception as e:
            st.exception(e)
