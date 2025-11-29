# SPDX-License-Identifier: GPL-3.0-only
"""
Componenti UI per lo wizard di onboarding semantico (pagina Semantics).

Qui teniamo tutta la logica "grafica":
- layout a 3 colonne (descrizione, pulsante, stato)
- progress bar complessiva
- loader/spinner per i passi lunghi
- testi DIKW di contesto

La pagina semantics.py si limita a:
- fare il gating (client_state, book_ready, ecc.)
- passare slug e le funzioni di azione (convert, enrich, summary, preview)
"""

from __future__ import annotations

from typing import Callable, Dict

import streamlit as st

from ui.semantic_progress import (
    SEMANTIC_STEP_IDS,
    STEP_CONVERT,
    STEP_ENRICH,
    STEP_PREVIEW,
    STEP_SUMMARY,
    get_semantic_progress,
    mark_semantic_step_done,
)

ActionFn = Callable[[], None]


def _maybe_divider() -> None:
    divider_fn = getattr(st, "divider", None)
    if callable(divider_fn):
        divider_fn()


def _maybe_progress(value: float | int) -> None:
    progress_fn = getattr(st, "progress", None)
    if callable(progress_fn):
        progress_fn(value)


def _render_step_row(
    step_number: int,
    step_id: str,
    title: str,
    description: str,
    button_label: str,
    action: ActionFn | None,
    enabled: bool,
    slug: str,
    progress: Dict[str, bool],
    busy_text: str,
) -> None:
    """
    Disegna una riga dello wizard:

    | Passo + descrizione | Pulsante azione | Stato (icona + testo) |
    """
    col_desc, col_button, col_status = st.columns([4, 1.6, 1])

    # Colonna 1: titolo e descrizione
    with col_desc:
        st.markdown(f"**Passo {step_number} – {title}**")
        st.caption(description)

    # Colonna 2: pulsante
    with col_button:
        clicked = st.button(
            button_label,
            key=f"btn_semantic_{step_id}",
            disabled=not enabled,
        )
        if clicked and enabled and action is not None:
            # Loader/Spinner durante l'azione
            with st.spinner(busy_text):
                action()
            # Stato completato (persistente)
            mark_semantic_step_done(slug, step_id)
            progress[step_id] = True

    # Colonna 3: stato (icona + testo)
    with col_status:
        done = bool(progress.get(step_id))
        if done:
            st.markdown("✅ **Fatto**")
        else:
            if enabled:
                st.markdown("⏳ *Da fare*")
            else:
                st.markdown("⏹️ *In attesa*")


def render_semantic_wizard(
    *,
    slug: str,
    client_state_ok: bool,
    book_ready: bool,
    actions: Dict[str, ActionFn],
) -> None:
    """
    Renderizza l'intero wizard a 4 passi.

    Parameters
    ----------
    slug:
        Identificativo del cliente.
    client_state_ok:
        True se lo stato del cliente consente le azioni semantiche (DIKW).
    book_ready:
        True se la cartella book/ è pronta per la preview.
    actions:
        Dizionario delle azioni:
        {
          "convert": callable,
          "enrich": callable,
          "summary": callable,
          "preview": callable,
        }
    """
    if not slug:
        st.warning("Seleziona prima un cliente valido.")
        return

    # Stato dei passi (persistente per cliente)
    progress = get_semantic_progress(slug)

    # Header + DIKW
    st.subheader("Onboarding semantico")
    st.caption(
        "DIKW: da **Data** (PDF/raw e tag grezzi) a **Information** "
        "(Markdown chunkizzati con frontmatter); "
        "**Knowledge** si ottiene arricchendo i frontmatter e generando "
        "README/SUMMARY, quindi la preview è la vista finale."
    )

    _maybe_divider()

    # Progress bar complessiva (0/4, 1/4, ...)
    total_steps = len(SEMANTIC_STEP_IDS)
    completed_steps = sum(1 for v in progress.values() if v)

    if total_steps > 0:
        _maybe_progress(completed_steps / total_steps)
    st.caption(f"{completed_steps}/{total_steps} passi completati")

    _maybe_divider()

    # ---- Passo 1: Converti PDF in Markdown ----
    _render_step_row(
        step_number=1,
        step_id=STEP_CONVERT,
        title="Converti PDF in Markdown",
        description=(
            "Trasforma tutti i PDF in `raw/` nei corrispondenti file Markdown "
            "chunkizzati, con frontmatter base (titolo, categoria, file sorgente, "
            "timestamp, `tags_raw`)."
        ),
        button_label="Converti PDF in Markdown",
        action=actions.get("convert"),
        enabled=client_state_ok,
        slug=slug,
        progress=progress,
        busy_text="Conversione PDF → Markdown in corso…",
    )

    _maybe_divider()

    # ---- Passo 2: Arricchisci frontmatter ----
    _render_step_row(
        step_number=2,
        step_id=STEP_ENRICH,
        title="Arricchisci frontmatter",
        description=(
            "Usa il vocabolario canonico e le entità approvate per aggiornare i "
            "frontmatter con tag normalizzati, `entities` e `relations_hint`."
        ),
        button_label="Arricchisci frontmatter",
        action=actions.get("enrich"),
        enabled=client_state_ok,
        slug=slug,
        progress=progress,
        busy_text="Arricchimento semantico del frontmatter in corso…",
    )

    _maybe_divider()

    # ---- Passo 3: Genera README/SUMMARY ----
    _render_step_row(
        step_number=3,
        step_id=STEP_SUMMARY,
        title="Genera README/SUMMARY",
        description=(
            "Rigenera `README.md` e `SUMMARY.md` in base ai Markdown aggiornati "
            "e al mapping, così la KB è navigabile e coerente."
        ),
        button_label="Genera README/SUMMARY",
        action=actions.get("summary"),
        enabled=client_state_ok,
        slug=slug,
        progress=progress,
        busy_text="Generazione di README e SUMMARY in corso…",
    )

    _maybe_divider()

    # ---- Passo 4: Vai alla preview Docker (HonKit) ----
    _render_step_row(
        step_number=4,
        step_id=STEP_PREVIEW,
        title="Vai all’anteprima Docker (HonKit)",
        description=(
            "Apri la pagina di preview Docker per controllare la knowledge base " "così come la vedranno gli utenti."
        ),
        button_label="Vai alla preview Docker",
        action=actions.get("preview"),
        enabled=(client_state_ok and book_ready),
        slug=slug,
        progress=progress,
        busy_text="Apertura della pagina di preview…",
    )
