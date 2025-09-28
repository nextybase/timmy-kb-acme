# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/landing_slug.py
from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, open_for_read_bytes_selfguard, read_text_safe
from pre_onboarding import ensure_local_workspace_for_ui
from ui.services import vision_provision as vision_services

st: Any | None
try:  # preferisce runtime soft-fail per import opzionali
    import streamlit as _st

    st = _st
except Exception:  # pragma: no cover
    st = None

CLIENT_CONTEXT_ERROR_MSG = (
    "ClientContext non disponibile. Esegui " "pre_onboarding.ensure_local_workspace_for_ui o imposta REPO_ROOT_DIR."
)


def _reset_to_landing() -> None:
    """Reimposta lo stato UI e torna alla landing (slug vuoto)."""
    if st is None:
        return
    preserve = {"phase"}
    for key in list(st.session_state.keys()):
        if key not in preserve:
            st.session_state.pop(key, None)
    st.session_state["slug"] = ""
    try:
        st.rerun()
    except Exception:
        pass


def _workspace_dir_for(slug: str) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "output" / f"timmy-kb-{slug}"


def _request_shutdown(logger: Optional[logging.Logger]) -> None:
    try:
        (logger or logging.getLogger("ui.landing_slug")).info("ui.shutdown_request")
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


def _base_dir_for(slug: str) -> Path:
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


def _render_logo() -> None:
    if st is None:
        return
    try:
        root = Path(__file__).resolve().parents[2]
        logo = root / "assets" / "next-logo.png"
        if not logo.exists():
            return
        import base64 as _b64

        logo_path = ensure_within_and_resolve(root, logo)
        with open_for_read_bytes_selfguard(logo_path) as logo_file:
            encoded = _b64.b64encode(logo_file.read()).decode("ascii")
        left, right = st.columns([4, 1])
        with right:
            st.markdown(
                (
                    "<img src='data:image/png;base64,"
                    f"{encoded}"
                    "' alt='NeXT' style='width:100%;height:auto;display:block;' />"
                ),
                unsafe_allow_html=True,
            )
    except Exception:  # pragma: no cover
        pass


def _enter_existing_workspace(slug: str, fallback_name: str) -> Tuple[bool, str, str]:
    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")
    client_name: str = fallback_name or slug
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
        from pipeline.config_utils import get_client_config

        cfg = get_client_config(ctx) or {}
        client_name = str(cfg.get("client_name") or slug)
    except Exception:  # pragma: no cover
        client_name = fallback_name or slug

    st.session_state["slug"] = slug
    st.session_state["client_name"] = client_name
    st.session_state["client_locked"] = True
    st.session_state["active_section"] = "Configurazione"
    st.session_state.pop("vision_workflow", None)
    try:
        st.rerun()
    except Exception:  # pragma: no cover
        pass
    return True, slug, client_name


def render_landing_slug(log: Optional[logging.Logger] = None) -> Tuple[bool, str, str]:
    """Landing slug-first con verifica e bootstrap Vision Statement."""

    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")

    st.markdown("<div style='height: 6vh'></div>", unsafe_allow_html=True)
    _render_logo()

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
        st.button("Esci", on_click=lambda: _request_shutdown(log), use_container_width=True)

    slug = slug.strip()
    if not slug:
        return False, "", ""

    vision_state = cast(Optional[Dict[str, Any]], st.session_state.get("vision_workflow"))
    if not vision_state or vision_state.get("slug") != slug:
        vision_state = {
            "slug": slug,
            "client_name": "",
            "verified": False,
            "needs_creation": False,
            "pdf_bytes": None,
            "pdf_filename": None,
            "workspace_created": False,
            "base_dir": None,
            "yaml_paths": {},
            "mapping_yaml": "",
            "cartelle_yaml": "",
        }
        st.session_state["vision_workflow"] = vision_state

    workspace_dir = _workspace_dir_for(slug)
    workspace_exists = workspace_dir.exists()

    if st.button("Verifica cliente", key="ls_verify"):
        if workspace_exists:
            return _enter_existing_workspace(slug, vision_state.get("client_name", ""))
        vision_state["verified"] = True
        vision_state["needs_creation"] = True
        st.session_state["vision_workflow"] = vision_state
        st.success("Cliente nuovo: carica il Vision Statement e crea il workspace.")

    if not vision_state.get("verified", False):
        return False, slug, vision_state.get("client_name", "")

    client_name = st.text_input(
        "Nome cliente",
        value=vision_state.get("client_name", ""),
        key="ls_name",
    ).strip()
    vision_state["client_name"] = client_name

    uploaded_pdf = st.file_uploader(
        "Vision Statement (PDF)",
        type=["pdf"],
        accept_multiple_files=False,
        key="ls_pdf",
        help="Carica il Vision Statement. Verrà salvato come config/VisionStatement.pdf quando crei il workspace.",
    )
    if uploaded_pdf is not None:
        raw_pdf = uploaded_pdf.read()
        if raw_pdf:
            vision_state["pdf_bytes"] = raw_pdf
            vision_state["pdf_filename"] = uploaded_pdf.name
            st.success(f"PDF caricato: {uploaded_pdf.name}")
        else:
            st.warning("File PDF vuoto: riprova il caricamento.")
        st.session_state["vision_workflow"] = vision_state

    create_disabled = not client_name or vision_state.get("pdf_bytes") is None
    if st.button("Crea workspace + carica PDF", key="ls_create_workspace", type="primary", disabled=create_disabled):
        pdf_bytes = cast(Optional[bytes], vision_state.get("pdf_bytes"))
        if not pdf_bytes:
            st.error("Carica il Vision Statement prima di procedere.")
        else:
            try:
                ensure_local_workspace_for_ui(slug, client_name or slug, vision_statement_pdf=pdf_bytes)
                ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
                if ctx.base_dir is None:
                    raise ConfigError("Workspace creato ma base_dir non disponibile.")
                base_dir = Path(ctx.base_dir)
                vision_state["base_dir"] = str(base_dir)
                pdf_path = ensure_within_and_resolve(base_dir, base_dir / "config" / "VisionStatement.pdf")
                result = vision_services.provision_from_vision(
                    ctx,
                    log or logging.getLogger("ui.vision_provision"),
                    slug=slug,
                    pdf_path=pdf_path,
                )
                yaml_paths = cast(Dict[str, str], result.get("yaml_paths") or {})
                vision_state["yaml_paths"] = yaml_paths
                vision_state["workspace_created"] = True
                vision_state["needs_creation"] = False
                st.session_state["slug"] = slug
                st.session_state["client_name"] = client_name or slug
                st.success("Workspace creato e YAML generati.")
                try:
                    mapping_abs = str(ensure_within_and_resolve(base_dir, Path(yaml_paths.get("mapping", ""))))
                    cartelle_abs = str(ensure_within_and_resolve(base_dir, Path(yaml_paths.get("cartelle_raw", ""))))
                    st.json({"mapping": mapping_abs, "cartelle_raw": cartelle_abs}, expanded=False)
                except Exception:
                    pass
            except ConfigError as exc:
                if log:
                    log.warning("landing.workspace_creation_failed", extra={"slug": slug, "error": str(exc)})
                st.error(str(exc))
            except Exception:  # pragma: no cover
                if log:
                    log.exception("landing.workspace_creation_failed", extra={"slug": slug})
                st.error("Errore durante la creazione del workspace. Controlla i log.")
            finally:
                st.session_state["vision_workflow"] = vision_state

    if not vision_state.get("workspace_created"):
        return False, slug, client_name

    base_dir_str = cast(Optional[str], vision_state.get("base_dir"))
    yaml_paths = cast(Dict[str, str], vision_state.get("yaml_paths") or {})
    if not base_dir_str or "mapping" not in yaml_paths or "cartelle_raw" not in yaml_paths:
        st.warning("Workspace creato ma non sono disponibili gli YAML generati.")
        return False, slug, client_name

    base_dir_path = Path(base_dir_str)
    try:
        mapping_path = ensure_within_and_resolve(base_dir_path, Path(yaml_paths["mapping"]))
        cartelle_path = ensure_within_and_resolve(base_dir_path, Path(yaml_paths["cartelle_raw"]))
        mapping_content = read_text_safe(base_dir_path, mapping_path, encoding="utf-8")
        cartelle_content = read_text_safe(base_dir_path, cartelle_path, encoding="utf-8")
    except Exception:  # pragma: no cover
        mapping_content = vision_state.get("mapping_yaml", "")
        cartelle_content = vision_state.get("cartelle_yaml", "")
    else:
        vision_state["mapping_yaml"] = mapping_content
        vision_state["cartelle_yaml"] = cartelle_content
        st.session_state["vision_workflow"] = vision_state

    st.markdown("### YAML generati (modificabili)")

    with st.form("mapping_yaml_editor"):
        updated_vision = st.text_area(
            "semantic/semantic_mapping.yaml",
            value=vision_state.get("mapping_yaml", ""),
            height=280,
        )
        if st.form_submit_button("Salva semantic_mapping.yaml"):
            try:
                target = ensure_within_and_resolve(base_dir_path, Path(yaml_paths["mapping"]))
                safe_write_text(target, updated_vision)
                vision_state["mapping_yaml"] = updated_vision
                st.success("semantic_mapping.yaml aggiornato.")
            except Exception:  # pragma: no cover
                if log:
                    log.exception("landing.save_vision_failed", extra={"slug": slug})
                st.error("Impossibile salvare semantic_mapping.yaml. Controlla i log.")
            finally:
                st.session_state["vision_workflow"] = vision_state

    with st.form("cartelle_yaml_editor"):
        updated_cartelle = st.text_area(
            "semantic/cartelle_raw.yaml",
            value=vision_state.get("cartelle_yaml", ""),
            height=280,
        )
        if st.form_submit_button("Salva cartelle_raw.yaml"):
            try:
                target = ensure_within_and_resolve(base_dir_path, Path(yaml_paths["cartelle_raw"]))
                safe_write_text(target, updated_cartelle)
                vision_state["cartelle_yaml"] = updated_cartelle
                st.success("cartelle_raw.yaml aggiornato.")
            except Exception:  # pragma: no cover
                if log:
                    log.exception("landing.save_cartelle_failed", extra={"slug": slug})
                st.error("Impossibile salvare cartelle_raw.yaml. Controlla i log.")
            finally:
                st.session_state["vision_workflow"] = vision_state

    if st.button("Vai alla configurazione", key="ls_go_configuration", type="primary"):
        vision_state["workspace_committed"] = True
        st.session_state["vision_workflow"] = vision_state
        st.session_state["client_locked"] = True
        st.session_state["active_section"] = "Configurazione"
        try:
            st.rerun()
        except Exception:  # pragma: no cover
            pass

    return False, slug, client_name
