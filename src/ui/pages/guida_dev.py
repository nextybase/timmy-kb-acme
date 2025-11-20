# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/guida_dev.py
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, cast

from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()

from pipeline.path_utils import read_text_safe
from ui.chrome import render_chrome_then_require


def _repo_root() -> Path:
    # pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


DOCS_DIR = Path("docs")
_DOCS_DEFAULT = DOCS_DIR / "index.md"
_DOCS_EXCLUDE = {"index.md", "guida_ui.md"}


CacheDecorator = Callable[[Callable[[str], str]], Callable[[str], str]]
cache_markdown = cast(CacheDecorator, st.cache_data(show_spinner=False))


@cache_markdown
def _read_markdown(rel_path: str) -> str:
    """
    Lettura sicura e cacheata di un file Markdown relativo alla root del repo.
    Ritorna un messaggio di warning in caso di errore.
    """
    try:
        return cast(str, read_text_safe(_repo_root(), Path(rel_path)))
    except Exception as e:
        return f"> ⚠️ Impossibile leggere `{rel_path}`: {e}"


def _strip_links(markdown: str) -> str:
    """
    Disabilita i link Markdown trasformandoli in semplice testo.

    Esempio: [Developer Guide](docs/developer_guide.md) -> Developer Guide
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


def _list_docs_for_menu() -> list[tuple[str, str]]:
    """
    Restituisce l'elenco dei file Markdown disponibili nella cartella docs/,
    esclusi index.md e guida_ui.md.

    Ogni elemento è una tupla (title, rel_path) dove:
    - title: titolo estratto dal contenuto Markdown
    - rel_path: path relativo usato da _read_markdown (es. "docs/developer_guide.md")
    """
    try:
        docs_dir = _repo_root() / DOCS_DIR
        md_files = sorted(docs_dir.glob("*.md"))
    except Exception:
        return []

    items: list[tuple[str, str]] = []
    for p in md_files:
        if p.name in _DOCS_EXCLUDE:
            continue
        rel_path = str(DOCS_DIR / p.name)
        md = _read_markdown(rel_path)
        title = _extract_title(md) or p.stem
        items.append((title, rel_path))

    return items


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

docs_menu = _list_docs_for_menu()

# Titolo per l'indice (docs/index.md)
index_md = _read_markdown(str(_DOCS_DEFAULT))
index_title = _extract_title(index_md) or "Indice"

menu_labels = [index_title] + [title for title, _ in docs_menu]

selected_label = st.selectbox(
    "Seleziona un file di documentazione",
    options=menu_labels,
    index=0,
)

selected_index = menu_labels.index(selected_label)

# Di default mostriamo sempre docs/index.md.
if selected_index == 0:
    rel_path = str(_DOCS_DEFAULT)
else:
    _, rel_path = docs_menu[selected_index - 1]

md = _read_markdown(rel_path)

# Sull'indice vogliamo link non cliccabili.
if rel_path == str(_DOCS_DEFAULT):
    md = _strip_links(md)

st.markdown(md)
