from __future__ import annotations

from typing import Any

import streamlit as st

from ui.components.mapping_editor import (
    build_mapping,
    load_default_mapping,
    load_semantic_mapping,
    save_semantic_mapping,
    split_mapping,
    validate_categories,
)
from ui.utils.streamlit_fragments import show_error_with_details


def render_config_tab(*, log: Any, slug: str, client_name: str) -> None:
    st.subheader("Configurazione (mapping semantico)")
    try:
        mapping = load_semantic_mapping(slug)
    except Exception:
        mapping = load_default_mapping()

    cats, reserved = split_mapping(mapping)
    st.caption("Panoramica categorie (solo lettura)")
    st.json(cats, expanded=False)

    st.markdown("---")
    st.caption("Valida o salva il mapping completo")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Valida mapping", key="btn_validate_mapping", width="stretch"):
            err = validate_categories(cats, normalize_keys=True)
            st.success("Mapping valido.") if not err else st.error(f"Errore: {err}")
    with col2:
        if st.button("Salva mapping rivisto", key="btn_save_mapping_all", width="stretch"):
            try:
                new_map = build_mapping(cats, reserved, slug=slug, client_name=client_name, normalize_keys=True)
                path = save_semantic_mapping(slug, new_map)
                log.info({"event": "semantic_mapping_saved_all", "slug": slug, "path": str(path)})
                st.success("Mapping salvato.")
            except Exception as e:
                show_error_with_details(
                    log,
                    "Salvataggio mapping non riuscito. Controlla i log per i dettagli.",
                    e,
                    event="ui.config.mapping_save_failed",
                    extra={"slug": slug},
                )
