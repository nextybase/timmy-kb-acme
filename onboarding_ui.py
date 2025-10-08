# onboarding_ui.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Onboarding UI entrypoint.

- Riusa helper esistente per aggiungere <repo>/src a sys.path (scripts/smoke_e2e._add_paths),
  con fallback locale se non disponibile.
- Configurazione pagina Streamlit come prima istruzione UI.
- Wrapper che lascia passare RerunException (usato da st.rerun) e mostra gli altri errori
  in un expander "Dettagli tecnici".
- Nessuna modifica alla business-logic: delega a src.ui.app.main()

Aggiornamenti UI (non-breaking):
- Header compatto con stato cliente + link rapidi.
- Status/Toast più evidenti per operazioni lunghe (pattern riutilizzabile).
- Expander "Diagnostica" (percorsi, counts raw/book/semantic, log-tail e download logs).
- Sidebar con azioni rapide (es. refresh Drive).
"""

from __future__ import annotations

import importlib
import inspect
import logging
import sys
from pathlib import Path
from typing import Callable

# ------------------------------------------------------------------------------
# Path bootstrap: deve avvenire PRIMA di ogni import di pacchetto (streamlit/ui/src)
# ------------------------------------------------------------------------------

def _ensure_repo_src_on_sys_path() -> None:
    """Aggiunge <repo>/src a sys.path se assente (fallback)."""
    repo_root = Path(__file__).parent.resolve()
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _bootstrap_sys_path() -> None:
    """Tenta l'helper ufficiale del repo, poi fallback locale."""
    try:
        # Helper già presente nel repo di test/smoke
        from scripts.smoke_e2e import _add_paths as _repo_add_paths  # type: ignore
    except Exception:
        _ensure_repo_src_on_sys_path()
        return
    try:
        _repo_add_paths()
    except Exception:
        _ensure_repo_src_on_sys_path()


# Esegui bootstrap path il prima possibile
_bootstrap_sys_path()

REPO_ROOT = Path(__file__).resolve().parent

# ------------------------------------------------------------------------------
# Ora è sicuro importare streamlit e i moduli del progetto
# ------------------------------------------------------------------------------

import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException

from src.ui.app import (
    _setup_logging,
    main as app_main,
    render_home,
    render_manage,
    render_semantics,
)
from ui.utils.branding import get_favicon_path
from ui.utils import diagnostics as diag
from src.ui.app_core.layout import (
    render_client_header,
    render_sidebar_branding,
    render_sidebar_quick_actions,
    render_sidebar_skiplink_and_quicknav,
    render_sidebar_tab_switches,
)
from src.ui.app_core.state import STATE_SEM_READY, compute_home_enabled, compute_manage_enabled, normalize_state

ICON_REFRESH = "\U0001F504"


def compute_sem_enabled(phase: str | None, slug: str | None) -> bool:
    """Compat layer: replica la vecchia logica usando eventuali stub patchati dai test."""
    normalized = normalize_state(phase)
    if normalized not in STATE_SEM_READY:
        return False

    slug_value = (slug or "").strip()
    if not slug_value:
        return False

    probe = globals().get("has_raw_pdfs")
    if not callable(probe):
        from ui.utils.workspace import has_raw_pdfs as _default_has_raw_pdfs

        probe = _default_has_raw_pdfs

    ready, _ = probe(slug_value)
    return bool(ready)


_compute_sem_enabled = compute_sem_enabled


def _compute_manage_enabled(phase: str | None, slug: str | None) -> bool:
    """Compatibilità test: delega alla nuova implementazione del core state."""
    return compute_manage_enabled(phase, slug)


def _compute_home_enabled(phase: str | None, slug: str | None) -> bool:
    """Compatibilità test: delega alla nuova implementazione del core state."""
    return compute_home_enabled(phase, slug)


def _sidebar_skiplink_and_quicknav() -> None:
    """Compat layer: ripristina skiplink + quick-nav nella sidebar per i test legacy."""
    try:
        render_sidebar_skiplink_and_quicknav(st_module=st)
    except Exception:
        try:
            sidebar = st.sidebar
            renderer = getattr(sidebar, "html", None)
            if callable(renderer):
                renderer("<small><a href='#main'>Main</a></small>")
            else:
                sidebar.markdown("[Main](#main)")
        except Exception:
            pass

    app_module = importlib.import_module("src.ui.app")
    nav = getattr(app_module, "render_quick_nav_sidebar", None)
    if callable(nav):
        nav(sidebar=True)
def _resolve_slug(slug: str | None) -> str | None:
    candidates = [
        slug,
        st.session_state.get("ui.manage.selected_slug"),
        st.session_state.get("current_slug"),
        st.session_state.get("slug"),
    ]
    for candidate in candidates:
        if candidate:
            trimmed = str(candidate).strip()
            if trimmed:
                return trimmed.lower()
    return None


def _page_config() -> None:
    # UI: page config deve essere la prima chiamata Streamlit
    icon_path = get_favicon_path(REPO_ROOT)
    page_icon = str(icon_path) if icon_path.exists() else None
    st.set_page_config(
        page_title="Onboarding NeXT - Clienti",
        layout="wide",
        page_icon=page_icon,
        initial_sidebar_state="expanded",
    )


def _render_global_error(e: Exception) -> None:
    # UI: messaggio breve + toast non bloccante
    try:
        st.toast("Si è verificato un errore. Dettagli nei log/expander.", icon="info")
    except Exception:
        pass
    st.error("Errore. Apri i dettagli tecnici per maggiori informazioni.")
    with st.expander("Dettagli tecnici", expanded=False):
        st.exception(e)


# ----------------------------------------------------------------------
# UI add-ons (solo presentazione, nessun side-effect di business logic)
# ----------------------------------------------------------------------

def _diagnostics(slug: str | None) -> None:
    '''Expander con info utili al triage. Non tocca la business logic.'''

    with st.expander("🔎 Diagnostica", expanded=False):
        if not slug:
            st.write("Seleziona uno slug per mostrare dettagli.")
            return

        base_dir = diag.resolve_base_dir(slug)
        st.write(f"Base dir: `{base_dir or 'n/d'}`")

        summaries = diag.summarize_workspace_folders(base_dir)
        if summaries:
            def _fmt_count(data: tuple[int, bool]) -> str:
                count, truncated = data
                return f">={count}" if truncated else str(count)

            st.write(
                "raw/: **{raw}** file · book/: **{book}** · semantic/: **{semantic}**".format(
                    raw=_fmt_count(summaries["raw"]),
                    book=_fmt_count(summaries["book"]),
                    semantic=_fmt_count(summaries["semantic"]),
                )
            )
            if any(flag for _, flag in summaries.values()):
                st.caption(f"Conteggio limitato a {diag.MAX_DIAGNOSTIC_FILES} file per directory.")

        log_files = diag.collect_log_files(base_dir)
        safe_reader = diag.get_safe_reader()

        latest = log_files[0] if log_files else None
        if latest:
            tail = diag.tail_log_bytes(latest, safe_reader=safe_reader)
            if tail:
                st.code(tail.decode(errors="replace"))
            else:
                st.info("Log non leggibile.")

        if log_files:
            archive_bytes = diag.build_logs_archive(log_files, slug=slug, safe_reader=safe_reader)
            if archive_bytes:
                st.download_button(
                    "Scarica logs",
                    data=archive_bytes,
                    file_name=f"{slug}-logs.zip",
                    mime="application/zip",
                    width="stretch",
                )
            else:
                st.info("Impossibile preparare l'archivio dei log.")



def _refresh_drive_action(logger, slug: str | None) -> tuple[bool, str | None]:
    """Pulisce la cache Drive notificando l'esito alla sidebar."""
    try:
        from src.ui.app import _clear_drive_tree_cache
    except ImportError as exc:
        logger.warning("ui.sidebar.drive_cache_import_failed", extra={"error": str(exc), "action": "refresh_drive", "slug": slug})
        return False, f"Cache Drive non disponibile: {exc}"
    _clear_drive_tree_cache()
    logger.info("ui.sidebar.drive_cache_cleared", extra={"action": "refresh_drive", "slug": slug})
    return True, None


def _generate_dummy_workspace(slug: str | None) -> None:
    """Invoca il tool di generazione workspace dummy mostrando feedback inline."""
    target = (slug or "dummy").strip() or "dummy"
    try:
        from tools.gen_dummy_kb import main as gen_dummy_main
    except Exception as exc:  # pragma: no cover
        st.sidebar.error(f"Generazione dummy non disponibile: {exc}")
        return
    with st.spinner(f"Genero dataset dummy per '{target}'..."):
        try:
            exit_code = gen_dummy_main(["--slug", target])
        except SystemExit as sys_exc:  # pragma: no cover
            exit_code = sys_exc.code or 1
        except Exception as exc:  # pragma: no cover
            st.sidebar.error(f"Errore durante la generazione: {exc}")
            return
    if int(exit_code) == 0:
        st.sidebar.success(f"Dummy generato per '{target}'")
    else:
        st.sidebar.error("Generazione dummy terminata con errore")


def _request_shutdown_safe() -> None:
    """Richiede la chiusura dell'app gestendo ambienti privi del backend CLI."""
    try:
        from src.ui.app import _request_shutdown
    except Exception as exc:  # pragma: no cover
        st.sidebar.error(f"Chiusura non disponibile: {exc}")
        return
    try:
        _request_shutdown(_setup_logging())
    except Exception as exc:  # pragma: no cover
        st.sidebar.error(f"Impossibile chiudere l'app: {exc}")


TAB_HOME = "home"
TAB_MANAGE = "gestisci cliente"
TAB_SEM = "semantica"


def _init_tab_state(home_enabled: bool, manage_enabled: bool, sem_enabled: bool) -> None:
    """Inizializza/riconcilia la tab attiva in sessione, sempre chiamata."""
    active = st.session_state.get("active_tab")
    if active is None:
        st.session_state["active_tab"] = TAB_MANAGE if manage_enabled else TAB_HOME
        return
    if not home_enabled:
        st.session_state["active_tab"] = TAB_HOME
        return
    if active == TAB_HOME and manage_enabled:
        st.session_state["active_tab"] = TAB_MANAGE
        return
    if active == TAB_MANAGE and not manage_enabled:
        st.session_state["active_tab"] = TAB_HOME
    elif active == TAB_SEM and not sem_enabled:
        st.session_state["active_tab"] = TAB_HOME


def _render_tabs_router(active: str, slug: str | None, logger: logging.Logger | None = None) -> None:
    """Router tab-based. Delegates ai renderer di src.ui.app."""
    log = logger or logging.getLogger("ui.tabs.router")

    def _call_renderer(name: str, fn: Callable[..., None], **kwargs) -> bool:
        try:
            call_kwargs = kwargs
            if "logger" in kwargs:
                try:
                    params = inspect.signature(fn).parameters
                except (TypeError, ValueError):
                    params = {}
                accepts_logger = any(
                    param.kind is inspect.Parameter.VAR_KEYWORD or key == "logger"
                    for key, param in params.items()
                )
                if not accepts_logger:
                    call_kwargs = {k: v for k, v in kwargs.items() if k != "logger"}
            fn(**call_kwargs)
        except RerunException:
            raise
        except Exception as exc:
            event = f"ui.tabs.{name}_failed"
            extra = {"error": str(exc), "active_tab": active}
            if "slug" in kwargs and kwargs.get("slug") is not None:
                extra["slug"] = kwargs["slug"]
            log.exception(event, extra=extra)
            raise
        return True

    try:
        app_module = importlib.import_module("src.ui.app")
    except Exception:
        app_module = None

    if app_module is None:
        home_fn: Callable[..., None] | None = render_home
        manage_fn: Callable[..., None] | None = render_manage
        sem_fn: Callable[..., None] | None = render_semantics
        main_fn = app_main
    else:
        home_fn = getattr(app_module, "render_home", None)
        manage_fn = getattr(app_module, "render_manage", None)
        sem_fn = getattr(app_module, "render_semantics", None)
        main_fn = getattr(app_module, "main", app_main)

    if active == TAB_HOME and callable(home_fn) and _call_renderer("render_home", home_fn, logger=log):
        return
    if active == TAB_MANAGE and callable(manage_fn) and _call_renderer("render_manage", manage_fn, slug=slug, logger=log):
        return
    if active == TAB_SEM and callable(sem_fn) and _call_renderer("render_semantics", sem_fn, slug=slug, logger=log):
        return

    main_fn()


# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------

def run() -> None:
    _page_config()
    logger = _setup_logging()

    slug = None
    state = None
    try:
        from ui.clients_store import get_state

        try:
            from ui.session import get_current_slug

            slug = get_current_slug()
        except Exception as exc:
            logger.warning(
                "ui.run.get_current_slug_failed",
                extra={"error": str(exc)},
            )
            slug = st.session_state.get("current_slug")
        state = normalize_state(get_state(slug)) if slug else None
    except Exception as exc:
        logger.exception(
            "ui.run.state_load_failed",
            extra={"stage": "state_init", "error": str(exc)},
        )

    resolved_slug = _resolve_slug(slug)
    if resolved_slug:
        st.session_state["current_slug"] = resolved_slug
    home_enabled = compute_home_enabled(state, resolved_slug)
    manage_enabled = compute_manage_enabled(state, resolved_slug)
    sem_enabled = compute_sem_enabled(state, resolved_slug)

    try:
        _init_tab_state(home_enabled, manage_enabled, sem_enabled)
    except Exception as exc:
        logger.warning(
            "ui.run.init_tab_state_failed",
            extra={"error": str(exc), "slug": resolved_slug},
        )
        st.session_state["active_tab"] = TAB_HOME

    try:
        render_client_header(
            st_module=st,
            repo_root=REPO_ROOT,
            slug=resolved_slug,
            state=state,
        )
    except Exception as exc:
        logger.exception(
            "ui.run.client_header_failed",
            extra={"slug": resolved_slug, "state": state, "error": str(exc)},
        )

    try:
        render_sidebar_branding(st_module=st, repo_root=REPO_ROOT)
        render_sidebar_tab_switches(
            st_module=st,
            active_tab_key="active_tab",
            tab_home=TAB_HOME,
            tab_manage=TAB_MANAGE,
            tab_sem=TAB_SEM,
            home_enabled=home_enabled,
            manage_enabled=manage_enabled,
            sem_enabled=sem_enabled,
        )
        render_sidebar_quick_actions(
            st_module=st,
            slug=resolved_slug,
            icon_refresh=ICON_REFRESH,
            refresh_callback=lambda: _refresh_drive_action(logger, resolved_slug),
            generate_dummy_callback=lambda: _generate_dummy_workspace(resolved_slug),
            request_shutdown_callback=_request_shutdown_safe,
            logger=logger,
        )
        render_sidebar_skiplink_and_quicknav(st_module=st)
    except Exception as exc:
        logger.exception(
            "ui.run.sidebar_render_failed",
            extra={"slug": resolved_slug, "error": str(exc)},
        )

    try:
        _render_tabs_router(st.session_state.get("active_tab", TAB_HOME), resolved_slug, logger)
    except RerunException:
        raise
    except Exception as e:
        logger.exception(
            "ui.run.render_router_failed",
            extra={"active_tab": st.session_state.get("active_tab", TAB_HOME), "slug": resolved_slug, "error": str(e)},
        )
        _render_global_error(e)
        try:
            _diagnostics(resolved_slug)
        except Exception as diag_exc:
            logger.exception("ui.run.diagnostics_failed", extra={"slug": resolved_slug, "error": str(diag_exc)})


if __name__ == "__main__":
    run()
