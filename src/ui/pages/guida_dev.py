# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/guida_dev.py
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, cast

from ui.utils.docs_view import load_markdown, render_markdown
from ui.utils.repo_root import get_repo_root
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()

from ui.chrome import render_chrome_then_require

DOC_OPTIONS: list[tuple[str, str]] = [
    ("NeXT Onboarding - Documentazione (v1.0 Beta)", "docs/index.md"),
    ("Guide - Architettura del sistema", "system/architecture.md"),
    ("Guide - Developer Guide", "docs/developer/developer_guide.md"),
    ("Guide - Coding Rules", "docs/developer/coding_rule.md"),
    ("Guide - Interfaccia Streamlit", "docs/streamlit_ui.md"),
    ("Guide - Test suite", "docs/test_suite.md"),
    ("Policy - Policy di Versioning", "docs/versioning_policy.md"),
    ("Policy - Policy di Push", "docs/policy_push.md"),
    ("Policy - Security & Compliance", "docs/security.md"),
    ("ADR - Registro decisioni (ADR)", "docs/adr/README.md"),
    ("ADR - ADR 0001 - SQLite SSOT dei tag", "docs/adr/0001-sqlite-ssot-tags.md"),
    ("ADR - ADR 0002 - Separation secrets/config", "docs/adr/0002-separation-secrets-config.md"),
    ("ADR - ADR 0003 - Playwright E2E UI", "docs/adr/0003-playwright-e2e-ui.md"),
    ("ADR - ADR 0004 - NLP performance tuning", "docs/adr/0004-nlp-performance-tuning.md"),
    ("Observability - Observability Stack", "docs/observability.md"),
    ("Observability - Logging Events", "docs/logging_events.md"),
]


CacheDecorator = Callable[[Callable[[str], str]], Callable[[str], str]]
cache_markdown = cast(CacheDecorator, st.cache_data(show_spinner=False))


@cache_markdown
def _read_markdown(rel_path: str) -> str:
    """
    Lettura sicura e cacheata di un file Markdown relativo alla root del repo.
    Ritorna un messaggio di warning in caso di errore.
    """
    return cast(str, load_markdown(get_repo_root() / Path(rel_path)))


def _strip_links(markdown: str) -> str:
    """
        Disabilita i link Markdown trasformandoli in semplice testo.

    Esempio: [Developer Guide](docs/developer/developer_guide.md) -> Developer Guide
    """
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", markdown)


def _extract_title(markdown: str) -> str:
    """
    Estrae il primo heading Markdown (#, ##, ...) e lo usa come titolo.
    Ritorna stringa vuota se non trova heading.
    """
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # Rimuove i cancelletto iniziali e spazi.
            return stripped.lstrip("#").strip()
    return ""


# ---------- UI ----------
# Header + sidebar coerenti con le altre pagine; slug NON obbligatorio.
render_chrome_then_require(allow_without_slug=True)

st.subheader("Guida Dev")
st.caption(
    "Questa pagina visualizza la documentazione locale dalla cartella `docs/`. "
    "Di default viene mostrato `docs/index.md`, ma puoi scegliere altri file dal menu."
)

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

selected_label = st.selectbox(
    "Seleziona un file di documentazione",
    options=[label for label, _ in DOC_OPTIONS],
    index=0,
)

rel_path = dict(DOC_OPTIONS).get(selected_label, "docs/index.md")
md = _read_markdown(rel_path)

if rel_path == "docs/index.md":
    md = _strip_links(md)

render_markdown(st, md)
