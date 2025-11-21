#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# src/ui/pages/logs_panel.py
"""
Dashboard dei log globali della UI.

Step 1: focus sui log Streamlit salvati in `.timmykb/logs/`, con:
- selezione del file di log
- filtri per livello e testo
- tabella con le righe parsate.

Questa pagina NON richiede slug attivo: opera a livello globale.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pipeline.log_viewer import LogFileInfo, get_global_logs_dir, list_global_log_files, load_log_sample
from ui.chrome import render_chrome_then_require
from ui.utils.stubs import get_streamlit

st = get_streamlit()


def _matches_text(row: Dict[str, Any], query: str) -> bool:
    """Match case-insensitive su message/event/slug/file_path."""
    if not query:
        return True
    q = query.lower()
    for key in ("event", "message", "slug", "file_path"):
        val = row.get(key)
        if isinstance(val, str) and q in val.lower():
            return True
    return False


def main() -> None:
    # Chrome Admin: slug non richiesto
    render_chrome_then_require(
        allow_without_slug=True,
        title="Log dashboard",
        subtitle="Esplora i log globali della UI Streamlit salvati in `.timmykb/logs/`.",
    )

    log_dir = get_global_logs_dir()
    files: List[LogFileInfo] = list_global_log_files(max_files=20)

    if not files:
        st.info("Nessun file di log trovato. " "La cartella dei log globali attesa è:")
        st.code(str(log_dir))
        st.caption(
            "Apri l'app di onboarding, genera un po' di traffico (es. selezione cliente) "
            "e verifica che il logging sia correttamente configurato."
        )
        return

    with st.expander("Dettagli sui log", expanded=False):
        st.markdown(
            "- I log globali della UI sono salvati in "
            f"`{log_dir}`.\n"
            "- Ogni riga segue il formato strutturato definito in `logging_utils`, con "
            "metadati `key=value` (`slug`, `run_id`, `event`, `phase`, `file_path`, ...).\n"
            "- Questa dashboard mostra un estratto delle ultime righe per analisi rapide."
        )

    col_file, col_rows = st.columns([2, 1])
    with col_file:
        selected = st.selectbox(
            "File di log",
            options=files,
            format_func=lambda info: f"{info.name} — {info.human_mtime}",
        )
    with col_rows:
        max_rows = st.slider(
            "Righe recenti",
            min_value=100,
            max_value=2000,
            step=100,
            value=500,
            help="Numero massimo di righe recenti da caricare dal file selezionato.",
        )

    rows = load_log_sample(selected.path, max_lines=max_rows)
    if not rows:
        st.warning(
            "Il file di log esiste ma non contiene righe parsate nel formato atteso. "
            "Verifica la configurazione del logger strutturato."
        )
        return

    levels = sorted({r.get("level") for r in rows if r.get("level")})
    col_level, col_text = st.columns([1, 2])
    with col_level:
        selected_levels = st.multiselect(
            "Livelli",
            options=levels,
            default=levels,
            help="Filtra per livello log (INFO, WARNING, ERROR, ...).",
        )
    with col_text:
        text_filter = st.text_input(
            "Filtro testo",
            placeholder="Cerca in evento, messaggio, slug o percorso file...",
        )

    filtered = [
        r for r in rows if (not selected_levels or r.get("level") in selected_levels) and _matches_text(r, text_filter)
    ]

    st.caption(f"Mostrando {len(filtered)} eventi (su {len(rows)} righe parsate) " f"dal file `{selected.name}`.")
    st.dataframe(filtered)


if __name__ == "__main__":  # pragma: no cover - per debug manuale
    main()
