# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/landing_slug.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

try:
    import streamlit as st
except Exception as e:  # pragma: no cover
    raise RuntimeError("Streamlit non disponibile per la landing UI.") from e

# Facade semantica (opzionale)
_SemGetPaths = Callable[[str], Dict[str, Path]]
try:  # pragma: no cover - opzionale in ambienti minimi
    from semantic.api import get_paths as _sem_get_paths  # type: ignore[import-not-found]

    _sem_get_paths = _sem_get_paths  # satisfy linters about redefinition
except Exception:  # pragma: no cover
    _sem_get_paths = None  # type: ignore[assignment]


def _base_dir_for(slug: str) -> Path:
    """Calcola la base directory per lo slug, preferendo semantic.api se disponibile."""
    if _sem_get_paths is not None and slug:
        try:
            paths = _sem_get_paths(slug)  # type: ignore[misc]
            base = paths["base"]
            return base if isinstance(base, Path) else Path(str(base))
        except Exception:
            pass
    return Path("output") / f"timmy-kb-{slug}"


def render_landing_slug(log: Optional[logging.Logger] = None) -> Tuple[bool, str, str]:
    """Landing minimale: inizialmente solo slug; su slug nuovo mostra Nome+PDF+help.

    Restituisce: (locked, slug, client_name)
    """
    st.markdown("<div style='height: 6vh'></div>", unsafe_allow_html=True)

    # Banner in alto a destra (landing)
    try:
        ROOT = Path(__file__).resolve().parents[2]
        _logo = ROOT / "assets" / "next-logo.png"
        if _logo.exists():
            import base64 as _b64

            _data = _logo.read_bytes()
            _enc = _b64.b64encode(_data).decode("ascii")
            img_html = (
                "<img src='data:image/png;base64,"
                f"{_enc}"
                "' alt='NeXT' "
                "style='width:100%;height:auto;display:block;' />"
            )
            left, right = st.columns([4, 1])
            with right:
                st.markdown(img_html, unsafe_allow_html=True)
    except Exception:
        pass

    # Input slug centrato (unico elemento iniziale)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        slug: str = (
            st.text_input(
                "Slug cliente",
                value=st.session_state.get("slug", ""),
                key="ls_slug",
                placeholder="es. acme",
            )
            or ""
        )

    slug = (slug or "").strip()
    if not slug:
        return False, "", ""

    base_dir = _base_dir_for(slug)

    # Caso A: workspace esistente → carica nome da config se presente
    if base_dir.exists():
        client_name: str = slug
        try:
            # Carica config se presente per recuperare il nome
            from pipeline.config_utils import get_client_config
            from pipeline.context import ClientContext

            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            cfg = get_client_config(ctx) or {}
            client_name = str(cfg.get("client_name") or slug)
        except Exception:
            client_name = slug

        st.session_state["slug"] = slug
        st.session_state["client_name"] = client_name
        st.session_state["client_locked"] = True
        st.session_state["active_section"] = "Configurazione"
        # Allinea comportamento al caso B: forza un rerun per pulire la landing
        try:
            st.rerun()
        except Exception:
            pass
        return True, slug, client_name

    # Caso B: workspace NON esiste → chiedi Nome + upload PDF e crea workspace
    st.caption("Nuovo cliente rilevato.")
    client_name: str = (
        st.text_input(
            "Nome cliente",
            value=st.session_state.get("client_name", ""),
            key="ls_name",
        )
        or ""
    )
    pdf = st.file_uploader(
        "Vision Statement (PDF)",
        type=["pdf"],
        accept_multiple_files=False,
        key="ls_pdf",
        help=(
            "Carica il Vision Statement (PDF). Verrà archiviato nel workspace del cliente "
            "e potrà essere aggiornato in seguito."
        ),
    )
    st.info(
        "Carica il Vision Statement (PDF). Verrà archiviato nel workspace del cliente "
        "e potrà essere aggiornato in seguito.",
        icon="ℹ️",
    )

    disabled = not (slug and client_name and pdf is not None)
    if st.button("Crea workspace cliente", key="ls_create_ws", disabled=disabled, type="primary"):
        try:
            from pre_onboarding import ensure_local_workspace_for_ui

            pdf_bytes = pdf.getvalue() if pdf is not None else None
            _ = ensure_local_workspace_for_ui(
                slug, client_name=client_name, vision_statement_pdf=pdf_bytes
            )
            if log:
                log.info(
                    {
                        "event": "ui_landing_workspace_created",
                        "slug": slug,
                        "base": str(base_dir),
                    }
                )

            st.session_state["slug"] = slug
            st.session_state["client_name"] = client_name
            st.session_state["client_locked"] = True
            st.session_state["active_section"] = "Configurazione"
            st.success("Workspace creato con successo.")
            st.rerun()
        except Exception as e:  # pragma: no cover
            st.exception(e)

    return False, slug, client_name
