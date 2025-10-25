# SPDX-License-Identifier: GPL-3.0-or-later
"""
Secrets Healthcheck: panoramica delle variabili d'ambiente sensibili.
- Mostra stato ✅/❌ senza rivelare i valori.
- Offre un punto di copia del nome variabile e link alla documentazione .env.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.settings import Settings
from ui.chrome import render_chrome_then_require


def _status_emoji(present: bool, required: bool) -> str:
    if present:
        return "✅ Presente"
    if required:
        return "❌ Mancante"
    return "⚠️ Assente (opzionale)"


def _safe_lookup(name: str) -> bool:
    try:
        value = get_env_var(name, default=None)
    except KeyError:
        return False
    except Exception:
        return False
    return bool(value and str(value).strip())


def main() -> None:
    render_chrome_then_require(allow_without_slug=True)
    st.subheader("Secrets Healthcheck")
    st.write(
        "Controlla lo stato delle variabili d'ambiente richieste. "
        "I valori non vengono mai mostrati; copia il nome e aggiorna il tuo `.env` dove necessario."
    )

    try:
        ensure_dotenv_loaded()
    except Exception:
        pass

    catalog: List[Dict[str, Any]] = Settings.env_catalog()

    missing_required = False
    for item in catalog:
        name = str(item.get("name"))
        required = bool(item.get("required", False))
        description = str(item.get("description", ""))
        doc_url = item.get("doc_url")

        present = _safe_lookup(name)
        if required and not present:
            missing_required = True

        col_name, col_status, col_actions = st.columns([2, 2, 3])
        with col_name:
            st.markdown(f"**{name}**")
            if description:
                st.caption(description)
        with col_status:
            st.markdown(_status_emoji(present, required))
        with col_actions:
            st.text_input(
                label=f"Copia {name}",
                value=name,
                key=f"copy_env_{name}",
                help="Copia il nome della variabile e aggiornalo nel tuo .env.",
                label_visibility="collapsed",
                disabled=True,
            )
            if doc_url:
                st.markdown(f"[Documentazione .env]({doc_url})")
        st.markdown("---")

    if missing_required:
        st.error(
            "Alcune variabili obbligatorie risultano mancanti. Aggiorna il tuo `.env` prima di proseguire.",
            icon="🚫",
        )
    else:
        st.success("Tutte le variabili obbligatorie risultano impostate.", icon="✅")


if __name__ == "__main__":  # pragma: no cover
    main()
