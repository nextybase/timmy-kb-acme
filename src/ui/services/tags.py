# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ..components.yaml_editors import edit_semantic_mapping as _edit_semantic_mapping

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


def render_tags_editor(slug: str) -> None:
    """
    Aggrega gli editor YAML principali del workspace semantico.
    Mostra un'unica colonna con editor dei tag e quick link per mapping/cartelle.
    """
    if st is None:
        return

    st.caption("Editor YAML semantico (mapping).")
    _edit_semantic_mapping(slug)
