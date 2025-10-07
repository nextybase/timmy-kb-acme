"""Tab Gestione cliente e helper correlati."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, cast

from pipeline.exceptions import ConfigError
from pipeline.path_utils import validate_slug
from src.ui.app_services.drive_cache import _clear_drive_tree_cache, get_drive_tree_cache
from ui.clients_store import get_state, load_clients, set_state
from ui.services.drive_runner import download_raw_from_drive_with_progress
from ui.utils.logging import enrich_log_extra, show_success
from ui.utils.streamlit_fragments import run_fragment

from .home import (
    _cartelle_path,
    _load_yaml_text,
    _mapping_path,
    _safe_streamlit_rerun,
    _save_yaml_text,
    _ui_dialog,
    _validate_yaml_dict,
    _workspace_dir_for,
)

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

try:
    from streamlit.runtime.scriptrunner_utils.exceptions import RerunException
except Exception:  # pragma: no cover

    class RerunException(Exception):  # type: ignore[no-redef]
        def __init__(self, *args: Any, rerun_data: Any | None = None, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.rerun_data = rerun_data


try:
    from ui.components.drive_tree import render_drive_tree
except Exception:  # pragma: no cover
    render_drive_tree = None

try:
    from ui.components.diff_view import render_drive_local_diff
except Exception:  # pragma: no cover
    render_drive_local_diff = None

try:
    from ui.components.yaml_editors import edit_cartelle_raw, edit_semantic_mapping, edit_tags_reviewed
except Exception:  # pragma: no cover
    edit_semantic_mapping = None
    edit_cartelle_raw = None
    edit_tags_reviewed = None

try:
    from ui.services.tags_adapter import run_tags_update
except Exception:  # pragma: no cover
    run_tags_update = None

_drive_tree_cached = get_drive_tree_cache()

__all__ = ["render_manage", "_render_manage_client_block"]


def _ui_delete_client_via_tool(slug: str) -> tuple[bool, str]:
    """UI adapter che invoca il tool CLI per eliminare il cliente."""
    try:
        validate_slug(slug)
    except ValueError as exc:
        return False, f"Slug non valido: {exc}"

    cmd = [sys.executable, "-m", "src.tools.clean_client_workspace", "--slug", slug, "-y"]
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        return False, f"Tool di cleanup non trovato: {exc}"
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        return False, message or "Errore durante l'eliminazione del cliente."
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
    output = (result.stdout or result.stderr or "").strip()
    return True, output or "Pulizia completata."


def _request_shutdown(logger: logging.Logger) -> None:
    try:
        slug_extra: Dict[str, Any] = {}
        try:
            if st is not None:
                current_slug = cast(Optional[str], st.session_state.get("slug"))
                if current_slug:
                    slug_extra["slug"] = current_slug
        except Exception:
            pass
        logger.info("ui.shutdown_request", extra=slug_extra or None)
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


def _render_manage_semantic_tab(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    mapping_rel = _mapping_path(workspace_dir)
    cartelle_rel = _cartelle_path(workspace_dir)
    mapping_key = f"ui.manage.{slug}.mapping_text"
    cartelle_key = f"ui.manage.{slug}.cartelle_text"

    if mapping_key not in st.session_state:
        try:
            st.session_state[mapping_key] = _load_yaml_text(workspace_dir, mapping_rel)
        except ConfigError:
            st.session_state[mapping_key] = ""
    if cartelle_key not in st.session_state:
        try:
            st.session_state[cartelle_key] = _load_yaml_text(workspace_dir, cartelle_rel)
        except ConfigError:
            st.session_state[cartelle_key] = ""

    with st.form(f"manage_semantic_form_{slug}"):
        st.text_area("semantic/semantic_mapping.yaml", key=mapping_key, height=320)
        st.text_area("semantic/cartelle_raw.yaml", key=cartelle_key, height=320)
        saved = st.form_submit_button(
            "Salva YAML",
            type="primary",
            width="stretch",
        )

    if saved:
        try:
            _validate_yaml_dict(st.session_state[mapping_key], "semantic_mapping.yaml")
            _validate_yaml_dict(st.session_state[cartelle_key], "cartelle_raw.yaml")
            mapping_rel.parent.mkdir(parents=True, exist_ok=True)
            cartelle_rel.parent.mkdir(parents=True, exist_ok=True)
            _save_yaml_text(workspace_dir, mapping_rel, st.session_state[mapping_key])
            _save_yaml_text(workspace_dir, cartelle_rel, st.session_state[cartelle_key])
            show_success("YAML aggiornati.")
            logger.info("ui.manage.semantic_saved", extra=enrich_log_extra({"slug": slug}))
        except ConfigError as exc:
            st.error(str(exc))


def render_quick_nav_sidebar(*, sidebar: bool = False) -> None:
    """Renderizza i link di navigazione rapida verso le sezioni principali."""
    target = st.sidebar if sidebar else st
    if target is None:
        return
    try:
        target.markdown("#### Navigazione rapida")
        target.markdown(
            "- [Drive](#section-drive)\n" "- [Editor YAML](#section-yaml)\n" "- [Semantica](#section-semantic)"
        )
    except Exception:
        pass


def _render_manage_client_block(logger: logging.Logger) -> None:
    try:
        clients = load_clients()
    except Exception as exc:  # pragma: no cover
        st.error("Impossibile caricare l'elenco clienti")
        st.caption(f"Dettaglio: {exc}")
        logger.warning("ui.manage.load_clients_failed", extra={"error": str(exc)})
        return

    if not clients:
        st.info("Nessun cliente registrato. Crea un nuovo cliente per iniziare.")
        st.session_state["ui.manage_slug"] = None
        st.session_state.pop("ui.manage.selected_slug", None)
        return

    feedback = st.session_state.pop("ui.manage.feedback", None)
    if feedback:
        status, message = feedback
        if status == "success":
            st.success(message)
        elif status == "error":
            st.error(message)
        elif status == "warning":
            st.warning(message)
        else:
            st.info(message)

    st.subheader("Gestisci cliente")
    slugs = [entry.slug for entry in clients]

    active_slug = st.session_state.get("ui.manage_slug")
    if active_slug and active_slug in slugs:
        st.session_state["ui.manage.selected_slug"] = active_slug
        if st.button(
            "Seleziona un altro cliente",
            key="ui.manage.change_client",
            type="secondary",
            width="stretch",
            help="Torna alla selezione clienti.",
        ):
            st.session_state["ui.manage_slug"] = None
            st.session_state.pop("ui.manage.selected_slug", None)
            _safe_streamlit_rerun()

        _render_manage_client_view(active_slug, logger)
        return

    selected_slug = st.session_state.get("ui.manage.selected_slug")
    if not selected_slug or selected_slug not in slugs:
        selected_slug = slugs[0] if slugs else None

    if slugs:
        try:
            selected = st.selectbox(
                "Cliente",
                options=slugs,
                index=slugs.index(selected_slug) if selected_slug else 0,
                key="ui.manage.selectbox",
                help="Seleziona un cliente dall'elenco.",
            )
        except Exception:  # pragma: no cover
            selected = st.selectbox("Cliente", options=slugs, key="ui.manage.selectbox")
    else:
        selected = None
    st.session_state["ui.manage.selected_slug"] = selected if selected else None

    st.session_state.setdefault("ui.manage.confirm_open", False)
    st.session_state.setdefault("ui.manage.confirm_target", None)

    col_manage, col_delete = st.columns([1, 1])

    with col_manage:
        if st.button(
            "Gestisci",
            key="ui.manage.button",
            type="primary",
            width="stretch",
            disabled=not selected,
        ):
            st.session_state["ui.manage_slug"] = selected
            logger.info("ui.manage.slug_selected", extra=enrich_log_extra({"slug": selected}))
            _safe_streamlit_rerun()

    with col_delete:
        if st.button(
            "Elimina",
            key=f"ui.manage.delete_button.{selected or 'none'}",
            width="stretch",
            disabled=not selected,
        ):
            if selected:
                st.session_state["ui.manage.confirm_open"] = True
                st.session_state["ui.manage.confirm_target"] = selected
                typed_key = f"ui.manage.confirm_typed.{selected}"
                if typed_key in st.session_state:
                    st.session_state.pop(typed_key)
                _safe_streamlit_rerun()

    if st.session_state.get("ui.manage.confirm_open"):
        target = st.session_state.get("ui.manage.confirm_target")
        if target:
            confirm_key = f"ui.manage.confirm_typed.{target}"

            def _delete_dialog_body() -> None:
                st.error("Azione irreversibile. Digita lo slug per confermare e poi premi elimina.")
                st.text_input("Scrivi lo slug esatto per confermare", key=confirm_key, placeholder=target)
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Annulla", key=f"ui.manage.cancel_delete.{target}", width="stretch"):
                        st.session_state["ui.manage.confirm_open"] = False
                        st.session_state["ui.manage.confirm_target"] = None
                        st.session_state.pop(confirm_key, None)
                        _safe_streamlit_rerun()
                with c2:
                    confirmed = st.session_state.get(confirm_key, "") == target
                    if st.button(
                        "Elimina definitivamente",
                        key=f"ui.manage.confirm_delete.{target}",
                        type="primary",
                        width="stretch",
                        disabled=not confirmed,
                    ):
                        with st.spinner(f"Elimino '{target}' da locale, DB e Drive..."):
                            ok, message = _ui_delete_client_via_tool(target)
                        if ok:
                            st.session_state["ui.manage.feedback"] = ("success", f"Cliente '{target}' eliminato.")
                            st.session_state["ui.manage.confirm_open"] = False
                            st.session_state["ui.manage.confirm_target"] = None
                            st.session_state.pop(confirm_key, None)
                            if target == st.session_state.get("ui.manage_slug"):
                                st.session_state.pop("ui.manage_slug", None)
                            st.session_state["ui.manage.selected_slug"] = None
                            _safe_streamlit_rerun()
                        else:
                            st.error(f"Errore eliminazione: {message}")

            _ui_dialog(f"Conferma eliminazione '{target}'", _delete_dialog_body)

    slug = st.session_state.get("ui.manage_slug")
    if not slug:
        st.info("Seleziona un cliente e premi 'Gestisci' per accedere agli strumenti dedicati.")
        return

    _render_manage_client_view(slug, logger)


def _render_manage_client_view(slug: str, logger: logging.Logger | None = None) -> None:
    logger = logger or logging.getLogger("ui.manage_client")
    workspace_dir = _workspace_dir_for(slug)

    st.subheader(f"Gestisci cliente - {slug}")
    if workspace_dir.exists():
        st.caption(f"Workspace: {workspace_dir}")
    else:
        st.warning("Workspace locale non trovato. Alcune funzionalità potrebbero non funzionare.")

    render_quick_nav_sidebar()

    raw_dir = workspace_dir / "raw"
    raw_exists = raw_dir.exists() and raw_dir.is_dir()

    st.session_state.setdefault("ui.busy.download_raw", False)
    st.session_state.setdefault("ui.busy.extract_tags", False)

    download_busy = bool(st.session_state.get("ui.busy.download_raw"))
    download_available = callable(download_raw_from_drive_with_progress)
    extract_busy = bool(st.session_state.get("ui.busy.extract_tags"))

    st.markdown("<a id='section-drive'></a>", unsafe_allow_html=True)
    col_drive, col_diff, col_tags = st.columns([3, 4, 3])
    drive_index: Dict[str, Dict[str, Any]] = {}

    with col_drive:
        st.subheader(f"Albero Drive (DRIVE_ID/{slug})")
        st.caption("Focus su raw/ e sottocartelle.")
        if callable(render_drive_tree):

            def _render_tree() -> Dict[str, Dict[str, Any]]:
                try:
                    return _drive_tree_cached(slug)
                except Exception as exc:  # pragma: no cover
                    _clear_drive_tree_cache()
                    st.error("Impossibile caricare l'albero Drive")
                    st.caption(f"Dettaglio: {exc}")
                    logger.warning(
                        "ui.manage.drive_tree_failed",
                        extra=enrich_log_extra({"slug": slug, "error": str(exc)}),
                    )
                    return {}

            drive_index = run_fragment(f"drive_tree.{slug}", _render_tree)
        else:
            st.info("Albero Drive non disponibile in questo ambiente.")

    with col_diff:
        st.subheader("Differenze Drive/Locale")
        download_clicked = st.button(
            "Scarica da Drive in raw/",
            type="primary",
            width="stretch",
            disabled=download_busy or not download_available,
            help="Scarica i PDF da DRIVE_ID/<slug>/raw/ nella cartella locale raw/.",
        )
        if download_clicked and download_available and not download_busy:
            st.session_state["ui.busy.download_raw"] = True
            status = None
            try:
                status = st.status("Scaricamento da Drive in corso...", expanded=True)
                with status:
                    status.write("Connessione a Drive...")
                    download_raw_from_drive_with_progress(slug=slug, logger=logger)
                    status.update(label="Scaricamento completato", state="complete", expanded=False)
                try:
                    set_state(slug, "pronto")
                    logger.info("ui.state.updated", extra=enrich_log_extra({"slug": slug, "state": "pronto"}))
                    st.toast("Stato cliente aggiornato a 'pronto'.")
                except Exception as state_exc:  # pragma: no cover
                    logger.warning(
                        "ui.state.update_failed",
                        extra=enrich_log_extra({"slug": slug, "error": str(state_exc)}),
                    )
                _clear_drive_tree_cache()
                show_success("Scaricamento completato")
                _safe_streamlit_rerun()
            except Exception as exc:  # pragma: no cover
                if status is not None:
                    status.update(label="Scaricamento interrotto", state="error", expanded=False)
                st.error("Scaricamento da Drive non riuscito")
                st.caption(f"Dettaglio: {exc}")
                logger.warning(
                    "ui.manage.download_raw_failed",
                    extra=enrich_log_extra({"slug": slug, "error": str(exc)}),
                )
            finally:
                st.session_state["ui.busy.download_raw"] = False
        elif download_clicked and not download_available:
            st.warning("Scaricamento da Drive non disponibile in questo ambiente.")

        if callable(render_drive_local_diff):

            def _render_diff() -> None:
                try:
                    render_drive_local_diff(slug, drive_index)
                except Exception as exc:  # pragma: no cover
                    st.error("Diff Drive/Locale non riuscito")
                    st.caption(f"Dettaglio: {exc}")
                    logger.warning(
                        "ui.manage.diff_failed",
                        extra=enrich_log_extra({"slug": slug, "error": str(exc)}),
                    )

            run_fragment(f"drive_diff.{slug}", _render_diff)
        else:
            st.info("Diff Drive/locale non ancora disponibile.")

    with col_tags:
        st.subheader("Tag revisionati")
        if callable(edit_tags_reviewed):
            try:
                edit_tags_reviewed(slug)
            except Exception as exc:  # pragma: no cover
                st.error("Impossibile mostrare tags_reviewed.yaml")
                st.caption(f"Dettaglio: {exc}")
                logger.warning(
                    "ui.manage.tags_editor_failed",
                    extra=enrich_log_extra({"slug": slug, "error": str(exc)}),
                )
        else:
            st.info("Editor tags non disponibile in questo ambiente.")

        extract_disabled = not raw_exists or not callable(run_tags_update) or extract_busy
        extract_clicked = st.button(
            "Estrai Tags",
            type="primary",
            width="stretch",
            disabled=extract_disabled,
            help="Aggiorna tags_reviewed.yaml analizzando i contenuti in raw/.",
        )
        if extract_clicked and callable(run_tags_update) and not extract_busy and raw_exists:
            st.session_state["ui.busy.extract_tags"] = True
            status = None
            try:
                status = st.status("Estrazione tag in corso...", expanded=True)
                with status:
                    status.write("Analisi dei PDF in raw/...")
                    run_tags_update(slug)
                    status.update(label="Estrazione completata", state="complete", expanded=False)
                st.success("Estrai Tags completato")
                st.toast("tags_reviewed.yaml aggiornato.")
                _safe_streamlit_rerun()
            except Exception as exc:  # pragma: no cover
                if status is not None:
                    status.update(label="Estrazione interrotta", state="error", expanded=False)
                st.error("Estrazione tag non riuscita")
                st.caption(f"Dettaglio: {exc}")
                logger.warning(
                    "ui.manage.tags_extract_failed",
                    extra=enrich_log_extra({"slug": slug, "error": str(exc)}),
                )
            finally:
                st.session_state["ui.busy.extract_tags"] = False
        elif extract_clicked and not raw_exists:
            st.warning("Cartella raw/ locale non disponibile.")
        elif extract_clicked and not callable(run_tags_update):
            st.warning("Adapter Estrai Tags non disponibile in questo ambiente.")

    st.markdown("<a id='section-yaml'></a><a id='section-semantic'></a>", unsafe_allow_html=True)
    st.subheader("Semantica")
    refresh_col, _ = st.columns([1, 3])
    if refresh_col.button(
        "Aggiorna elenco Drive",
        key=f"ui.manage.refresh_drive.{slug}",
        help="Rileggi l'albero su Drive e aggiorna le differenze Drive/Locale.",
        width="stretch",
    ):
        _clear_drive_tree_cache()
        toast_fn = getattr(st, "toast", None)
        if callable(toast_fn):
            toast_fn("Elenco Drive aggiornato. Ricalcolo in corso...")
        else:
            st.info("Elenco Drive aggiornato. Ricalcolo in corso...")
        try:
            _safe_streamlit_rerun()
        except Exception:
            pass

    state_val = (get_state(slug) or "").lower()
    eligible_states = {"pronto", "arricchito", "finito"}
    if state_val in eligible_states:
        sem_tabs = st.tabs(["Semantica"])
        with sem_tabs[0]:
            st.caption("Editor YAML semantici.")
            if callable(edit_semantic_mapping):
                edit_semantic_mapping(slug)
            if callable(edit_cartelle_raw):
                edit_cartelle_raw(slug)
    else:
        st.info("La semantica sarà disponibile quando lo stato raggiunge 'pronto' (dopo il download dei PDF in raw/).")


def render_manage(*, slug: str | None, logger: logging.Logger | None = None) -> None:
    """Gestione cliente con slug già risolto."""
    log = logger or logging.getLogger("ui.manage")
    slug_value = (slug or "").strip()
    if not slug_value:
        st.info("Seleziona un cliente per accedere alla gestione.")
        return
    try:
        _render_manage_client_view(slug_value, log)
    except RerunException:
        raise
    except Exception as exc:  # pragma: no cover
        log.warning("ui.manage.render_failed", extra=enrich_log_extra({"slug": slug_value, "error": str(exc)}))
        st.error("Impossibile caricare la gestione del cliente.")
