from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from pipeline.context import ClientContext
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme
from ui.clients_store import get_state, set_state
from ui.utils.streamlit_fragments import show_error_with_details
from ui.utils.workspace import has_raw_pdfs


def render_semantic_tab(*, log: Any, slug: str) -> None:
    """Tab Semantica: gestisce conversione, arricchimento e sintesi Markdown.
    Livello solo UI: non modifica la business logic né le API pubbliche.
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

    ready, raw_dir = has_raw_pdfs(slug)
    if not ready:
        st.warning("Scarica almeno un PDF in `raw/` prima di proseguire con la semantica.")
        with st.expander("Requisiti per la cartella raw/", expanded=False):
            st.markdown("- Verifica che `raw/` esista nel workspace locale.")
            st.markdown("- Assicurati che contenga almeno un file PDF valido.")
            if raw_dir is not None:
                st.markdown(f"- Cartella controllata: `{raw_dir}`.")
        return

    # UI: form unica per ridurre rerun e migliorare accessibilità
    with st.form("semantica_actions", clear_on_submit=False):
        cols = st.columns(3)
        with cols[0]:
            do_convert = st.form_submit_button(
                "1) Converti PDF in Markdown",
                help="Converte i PDF presenti in `raw/` in file Markdown sotto `book/`. Operazione idempotente.",
                width="stretch",
            )
        with cols[1]:
            do_enrich = st.form_submit_button(
                "2) Arricchisci frontmatter",
                help="Applica vocabolario revisionato e metadati ai Markdown in `book/`.",
                width="stretch",
            )
        with cols[2]:
            do_md = st.form_submit_button(
                "3) Genera SUMMARY e README",
                type="primary",
                help="Costruisce/valida `SUMMARY.md` e `README.md` nella cartella `book/`.",
                width="stretch",
            )

    def _toast_success(message: str) -> None:
        toast_fn = getattr(st, "toast", None)
        if callable(toast_fn):
            try:
                toast_fn(message, icon="✅")
                return
            except Exception:
                pass
        st.success(message)

    if do_convert:
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            convert_markdown(ctx, log, slug=slug)
            _toast_success("Conversione completata.")
        except Exception as e:  # pragma: no cover - UI
            show_error_with_details(
                log,
                "Conversione non completata. Controlla i log per i dettagli.",
                e,
                event="ui.semantic.convert_failed",
                extra={"slug": slug},
            )

    if do_enrich:
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            paths = get_paths(slug)
            base_dir: Path = ctx.base_dir or paths["base"]
            vocab = load_reviewed_vocab(base_dir, log)
            touched = enrich_frontmatter(ctx, log, vocab, slug=slug)
            _toast_success(f"Frontmatter arricchiti: {len(touched)}")
            set_state(slug, "arricchito")
        except Exception as e:  # pragma: no cover - UI
            show_error_with_details(
                log,
                "Arricchimento non completato. Controlla i log per i dettagli.",
                e,
                event="ui.semantic.enrich_failed",
                extra={"slug": slug},
            )

    if do_md:
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            write_summary_and_readme(ctx, log, slug=slug)
            _toast_success("SUMMARY.md e README.md generati/validati.")
            set_state(slug, "finito")
        except Exception as e:  # pragma: no cover - UI
            show_error_with_details(
                log,
                "Generazione README/SUMMARY non completata. Controlla i log per i dettagli.",
                e,
                event="ui.semantic.summary_failed",
                extra={"slug": slug},
            )
