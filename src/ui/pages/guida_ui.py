# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/guida_ui.py
from __future__ import annotations

from pathlib import Path
from typing import Callable, cast

import streamlit as st

from pipeline.path_utils import read_text_safe
from ui.chrome import render_chrome_then_require


def _repo_root() -> Path:
    # pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


CacheDecorator = Callable[[Callable[[str], str]], Callable[[str], str]]
cache_markdown = cast(CacheDecorator, st.cache_data(show_spinner=False))


@cache_markdown
def _read_markdown(rel_path: str) -> str:
    """
    Lettura sicura e cacheata di un file Markdown relativo alla root del repo.
    Ritorna un messaggio di warning in caso di errore.
    """
    try:
        return read_text_safe(_repo_root(), Path(rel_path))
    except Exception as e:
        return f"> ⚠️ Impossibile leggere `{rel_path}`: {e}"


# ---------- UI ----------
# Header + sidebar coerenti con le altre pagine; slug NON obbligatorio.
render_chrome_then_require(allow_without_slug=True)

st.subheader("Guida UI")
st.caption("Questa pagina visualizza la documentazione locale `docs/guida_ui.md`.")

# Aumenta SOLO il corpo del testo (p, li, dd, code/pre) lasciando invariati gli headings
st.html(
    """
<style>
/* Scope: contenitori markdown di Streamlit */
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li,
div[data-testid="stMarkdownContainer"] dd { font-size: 1.06rem; line-height: 1.85; }
div[data-testid="stMarkdownContainer"] code { font-size: .95rem; }
div[data-testid="stMarkdownContainer"] pre code { font-size: .90rem; }
</style>
"""
)

md = _read_markdown("docs/guida_ui.md")
st.markdown(md)
