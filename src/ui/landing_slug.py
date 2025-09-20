# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/landing_slug.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Tuple

from pipeline.path_utils import ensure_within_and_resolve, open_for_read_bytes_selfguard

st: Any | None
try:  # preferisce runtime soft-fail per import opzionali
    import streamlit as _st

    st = _st
except Exception:  # pragma: no cover
    st = None

CLIENT_CONTEXT_ERROR_MSG = (
    "ClientContext non disponibile. Esegui " "pre_onboarding.ensure_local_workspace_for_ui o imposta REPO_ROOT_DIR."
)


def _base_dir_for(slug: str) -> Path:
    """Calcola la base directory per lo slug usando esclusivamente ClientContext.

    ClientContext è lo SSoT per i path: in caso di indisponibilità si segnala l'errore.
    """
    try:
        from pipeline.context import ClientContext
    except Exception as exc:
        raise RuntimeError(CLIENT_CONTEXT_ERROR_MSG) from exc

    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    except Exception as exc:
        raise RuntimeError(CLIENT_CONTEXT_ERROR_MSG) from exc

    base = getattr(ctx, "base_dir", None)
    if isinstance(base, Path):
        return base

    raw_dir = getattr(ctx, "raw_dir", None)
    if isinstance(raw_dir, Path):
        return raw_dir.parent

    raise RuntimeError(CLIENT_CONTEXT_ERROR_MSG)


def render_landing_slug(log: Optional[logging.Logger] = None) -> Tuple[bool, str, str]:
    """Landing minimale: inizialmente solo slug; su slug nuovo mostra Nome+PDF+help.

    Restituisce: (locked, slug, client_name)
    """
    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")
    st.markdown("<div style='height: 6vh'></div>", unsafe_allow_html=True)

    # Banner in alto a destra
    try:
        ROOT = Path(__file__).resolve().parents[2]
        _logo = ROOT / "assets" / "next-logo.png"
        if _logo.exists():
            import base64 as _b64

            logo_path = ensure_within_and_resolve(ROOT, _logo)
            with open_for_read_bytes_selfguard(logo_path) as logo_file:
                _data = logo_file.read()
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

    # Input slug centrato
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

    base_dir: Optional[Path] = None
    base_dir_error: Optional[str] = None
    try:
        base_dir = _base_dir_for(slug)
    except RuntimeError as err:
        base_dir_error = str(err)

    # Caso A: workspace esistente → carica nome da config se presente
    if base_dir is not None and base_dir.exists():
        client_name: str = slug
        try:
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
        try:
            st.rerun()
        except Exception:
            pass
        return True, slug, client_name

    if base_dir_error:
        st.caption(base_dir_error)

    # Caso B: workspace nuovo → Nome + PDF
    st.caption("Nuovo cliente rilevato.")
    client_name = (
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
            _ = ensure_local_workspace_for_ui(slug, client_name=client_name, vision_statement_pdf=pdf_bytes)
            refreshed_base_dir: Optional[Path] = None
            try:
                refreshed_base_dir = _base_dir_for(slug)
            except RuntimeError as err:
                if log:
                    log.error(
                        {
                            "event": "ui_landing_workspace_created_ctx_missing",
                            "slug": slug,
                            "error": str(err),
                        }
                    )
                st.error(str(err))
                return False, slug, client_name
            if log:
                log.info(
                    {
                        "event": "ui_landing_workspace_created",
                        "slug": slug,
                        "base": str(refreshed_base_dir) if refreshed_base_dir is not None else "",
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
