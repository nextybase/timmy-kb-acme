from __future__ import annotations

from typing import Any

import streamlit as st

from ui.components.mapping_editor import (
    build_mapping,
    load_default_mapping,
    load_tags_reviewed,
    save_tags_reviewed,
    split_mapping,
    validate_categories,
)


def render_config_tab(*, log: Any, slug: str, client_name: str) -> None:
    st.subheader("Configurazione (mapping semantico)")
    try:
        mapping = load_tags_reviewed(slug)
    except Exception:
        mapping = load_default_mapping()

    cats, reserved = split_mapping(mapping)
    st.caption("Panoramica categorie (solo lettura)")
    st.json(cats, expanded=False)

    st.markdown("---")
    st.caption("Valida o salva il mapping completo")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Valida mapping", key="btn_validate_mapping"):
            err = validate_categories(cats, normalize_keys=True)
            st.success("Mapping valido.") if not err else st.error(f"Errore: {err}")
    with col2:
        if st.button("Salva mapping rivisto", key="btn_save_mapping_all"):
            try:
                new_map = build_mapping(cats, reserved, slug=slug, client_name=client_name, normalize_keys=True)
                path = save_tags_reviewed(slug, new_map)
                log.info({"event": "tags_reviewed_saved_all", "slug": slug, "path": str(path)})
                st.success("Mapping salvato.")
            except Exception as e:
                st.exception(e)
