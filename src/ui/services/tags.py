# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ..components.yaml_editors import edit_cartelle_raw as _edit_cartelle_raw
from ..components.yaml_editors import edit_semantic_mapping as _edit_semantic_mapping
from ..components.yaml_editors import edit_tags_reviewed as _edit_tags_reviewed

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

    st.caption("Editor YAML semantici (tags, mapping, cartelle_raw).")
    _edit_tags_reviewed(slug)
    st.divider()
    _edit_semantic_mapping(slug)
    st.divider()
    _edit_cartelle_raw(slug)
