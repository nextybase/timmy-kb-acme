from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

try:
    import streamlit as st  # type: ignore
except Exception as e:  # pragma: no cover
    raise RuntimeError("Streamlit non disponibile per la landing UI.") from e

# Facade semantica (opzionale)
try:  # pragma: no cover - opzionale in ambienti minimi
    from semantic.api import get_paths as _sem_get_paths  # type: ignore
except Exception:  # pragma: no cover
    _sem_get_paths = None  # type: ignore


def _base_dir_for(slug: str) -> Path:
    if _sem_get_paths is not None and slug:
        try:
            return _sem_get_paths(slug)["base"]  # type: ignore[index]
        except Exception:
            pass
    return Path("output") / f"timmy-kb-{slug}"


def render_landing_slug(log: Optional[logging.Logger] = None) -> Tuple[bool, str, str]:
    """Landing minimale: chiede solo lo slug; se manca il workspace, chiede Nome+PDF.

    Restituisce: (locked, slug, client_name)
    """
    st.markdown("<div style='height: 6vh'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(
            (
                "**Benvenuto!**\n\n"
                "- Inserisci lo `slug` del cliente (es. `acme`).\n"
                "- Se il workspace locale esiste, la UI lo carica e prosegue.\n"
                "- Se non esiste: inserisci anche il nome cliente e carica il PDF iniziale;\n"
                "  premi ‘Crea workspace cliente’ per creare la struttura standard.\n\n"
                "Nota: il PDF viene salvato come `config/VisionStatement.pdf` e il `config.yaml` viene aggiornato."
            )
        )

    slug = st.text_input("Slug cliente", value=st.session_state.get("slug", ""), key="ls_slug")
    slug = (slug or "").strip()
    if not slug:
        return False, "", ""

    base_dir = _base_dir_for(slug)

    # Caso A: workspace esistente → carica nome da config se presente
    if base_dir.exists():
        client_name = slug
        try:
            # Carica config se presente per recuperare il nome
            from pipeline.context import ClientContext  # type: ignore
            from pipeline.config_utils import get_client_config  # type: ignore

            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            cfg = get_client_config(ctx) or {}
            client_name = str(cfg.get("client_name") or slug)
        except Exception:
            client_name = slug

        st.session_state["slug"] = slug
        st.session_state["client_name"] = client_name
        st.session_state["client_locked"] = True
        return True, slug, client_name

    # Caso B: workspace NON esiste → chiedi Nome + upload PDF e crea workspace
    st.caption("Nuovo cliente: inserisci anche il nome e carica il PDF iniziale.")
    client_name = st.text_input(
        "Nome cliente", value=st.session_state.get("client_name", ""), key="ls_name"
    )
    pdf = st.file_uploader(
        "Vision Statement (PDF)", type=["pdf"], accept_multiple_files=False, key="ls_pdf"
    )

    disabled = not (slug and client_name and pdf is not None)
    if st.button("Crea workspace cliente", key="ls_create_ws", disabled=disabled, type="primary"):
        try:
            from pre_onboarding import ensure_local_workspace_for_ui  # type: ignore

            pdf_bytes = pdf.getvalue() if pdf is not None else None
            _ = ensure_local_workspace_for_ui(
                slug, client_name=client_name, vision_statement_pdf=pdf_bytes
            )
            if log:
                log.info(
                    {"event": "ui_landing_workspace_created", "slug": slug, "base": str(base_dir)}
                )

            st.session_state["slug"] = slug
            st.session_state["client_name"] = client_name
            st.session_state["client_locked"] = True
            st.success("Workspace creato con successo.")
            st.rerun()
        except Exception as e:  # pragma: no cover
            st.exception(e)

    return False, slug, client_name
