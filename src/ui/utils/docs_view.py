# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility condivise per visualizzare documentazione Markdown nella UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.utils.repo_root import get_repo_root

WARNING_PREFIX = "> Attenzione: impossibile leggere"


def load_markdown(path: Path) -> str:
    """
    Legge un file Markdown assicurando il perimetro del repository.

    - `path` puÒ² essere assoluto o relativo; viene validato rispetto alla repo root.
    - In caso di errore restituisce un messaggio Markdown di warning pronto per `st.markdown`.
    """
    repo_root = get_repo_root()
    try:
        target = ensure_within_and_resolve(repo_root, path)
    except Exception as exc:
        return f"{WARNING_PREFIX} `{path.as_posix()}`: {exc}"

    try:
        return cast(str, read_text_safe(repo_root, target))
    except Exception as exc:
        rel_repr = target.as_posix()
        try:
            rel_repr = target.relative_to(repo_root).as_posix()
        except Exception:
            rel_repr = target.as_posix()
        return f"{WARNING_PREFIX} `{rel_repr}`: {exc}"


def render_markdown(st: Any, content: str) -> None:
    """
    Wrapper minimale per rendere Markdown (es. documentazione) in Streamlit.
    Separato per centralizzare eventuali future personalizzazioni del rendering.
    """
    st.markdown(content)
