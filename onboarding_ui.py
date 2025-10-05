# onboarding_ui.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Onboarding UI entrypoint.

- Reuse existing repo helper to add <repo>/src to sys.path (scripts/smoke_e2e._add_paths),
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
import os
import sys
from pathlib import Path
from typing import Callable, Tuple

import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException

from src.ui.app import _setup_logging
from ui.utils.branding import get_favicon_path, render_brand_header, render_sidebar_brand

ICON_REFRESH = "\U0001F504"


STATE_MANAGE_READY = {"inizializzato", "pronto", "arricchito", "finito"}
STATE_SEM_READY = {"pronto", "arricchito", "finito"}


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


# ------------------------------------------------------------------------------
# Path bootstrap: prova ad usare l'helper del repo, con fallback locale
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
        from scripts.smoke_e2e import _add_paths as _repo_add_paths
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
# UI helpers
# ------------------------------------------------------------------------------


def _normalize_state(state: str | None) -> str:
    return (state or "").strip().lower()


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


def _client_header(*, slug: str | None, state: str | None) -> None:
    """Header della pagina principale senza caption aggiuntive."""
    _ = state
    subtitle = None
    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        subtitle=subtitle,
        include_anchor=True,
        show_logo=False,
    )
    if not slug:
        st.info("Nessun cliente selezionato. Usa **Nuovo Cliente** o **Gestisci cliente** dalla landing.")
        return


def _status_bar() -> Tuple[Callable[[str, str], None], Callable[[], None]]:
    """Area di stato leggera. Usare insieme a st.status nei flussi lunghi."""
    placeholder = st.empty()

    def update(msg: str, icon: str = "ℹ️") -> None:
        try:
            placeholder.info(f"{icon} {msg}")
        except Exception:
            pass

    def clear() -> None:
        placeholder.empty()

    return update, clear


def _diagnostics(slug: str | None) -> None:
    """Expander con info utili al triage. Non tocca la business logic."""
    with st.expander("🔎 Diagnostica", expanded=False):
        if not slug:
            st.write("Seleziona uno slug per mostrare dettagli.")
            return

        # Prova a ricostruire base_dir dal contesto del progetto (best-effort, UI only)
        try:
            from pipeline.context import ClientContext
        except Exception:
            base_dir = None
        else:
            try:
                ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
                base_dir = ctx.base_dir
            except Exception:
                base_dir = None

        st.write(f"Base dir: `{base_dir or 'n/d'}`")

        def _count_files(path: str | None) -> int:
            if not path or not os.path.isdir(path):
                return 0
            total = 0
            for _root, _dirs, files in os.walk(path):
                total += len(files)
            return total

        if base_dir:
            raw = Path(base_dir) / "raw"
            book = Path(base_dir) / "book"
            semantic = Path(base_dir) / "semantic"
            st.write(
                f"raw/: **{_count_files(str(raw))}** file · "
                f"book/: **{_count_files(str(book))}** · "
                f"semantic/: **{_count_files(str(semantic))}**"
            )

            logs_dir = Path(base_dir) / "logs"
            if logs_dir.is_dir():
                latest = None
                try:
                    files = sorted(
                        (p for p in logs_dir.iterdir() if p.is_file()),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    latest = files[0] if files else None
                except Exception:
                    latest = None

                if latest and latest.is_file():
                    try:
                        size = latest.stat().st_size
                        offset = max(0, size - 4000)
                        with latest.open("rb") as fh:
                            fh.seek(offset)
                            buf = fh.read(4000)
                        st.code(buf.decode(errors="replace"))
                    except Exception:
                        st.info("Log non leggibile.")

                # Zip dei log on-the-fly per download
                import io
                import zipfile

                mem = io.BytesIO()
                with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for f in logs_dir.iterdir():
                        if f.is_file():
                            zf.write(f, arcname=f.name)
                st.download_button(
                    "Scarica logs",
                    data=mem.getvalue(),
                    file_name=f"{slug}-logs.zip",
                    mime="application/zip",
                )


def _sidebar_brand() -> None:
    """Logo brand nella sidebar (tema-aware)."""
    try:
        render_sidebar_brand(st.sidebar, REPO_ROOT)
    except Exception:
        pass


def _sidebar_quick_actions(slug: str | None) -> None:
    st.sidebar.markdown("### Azioni rapide")
    st.sidebar.link_button("Guida UI", "https://github.com/nextybase/timmy-kb-acme/blob/main/docs/guida_ui.md")
    if st.sidebar.button(
        "Aggiorna elenco Drive",
        key="sidebar_refresh_drive",
        width="stretch",
    ):
        try:
            from src.ui.app import _clear_drive_tree_cache
        except ImportError as exc:
            st.sidebar.warning(f"Cache Drive non disponibile: {exc}")
        else:
            _clear_drive_tree_cache()
            _setup_logging().info("ui.sidebar.drive_cache_cleared")
            st.toast("Richiesta aggiornamento Drive inviata.", icon=ICON_REFRESH)
    if st.sidebar.button(
        "Genera dummy",
        key="sidebar_dummy_btn",
        width="stretch",
        help="Crea il workspace di esempio per testare il flusso.",
    ):
        _generate_dummy_workspace(slug)
    if st.sidebar.button("Esci", type="primary", width="stretch", help="Chiudi l'app"):
        _request_shutdown_safe()
    st.sidebar.markdown("---")


def _sidebar_skiplink_and_quicknav() -> None:
    """Inserisce skip-link e navigazione rapida in sidebar (best-effort)."""
    st.sidebar.markdown("<small><a href='#main' tabindex='0'>Main</a></small>", unsafe_allow_html=True)
    try:
        app_mod = importlib.import_module("src.ui.app")
    except Exception:
        return
    nav_fn = None
    for name in ("render_quick_nav_sidebar", "render_quick_nav", "render_quick_navigation", "quick_nav"):
        candidate = getattr(app_mod, name, None)
        if callable(candidate):
            nav_fn = candidate
            wrapper_attr = "__sidebar_only__"
            if not getattr(candidate, wrapper_attr, False):

                def _sidebar_only_nav(*, sidebar: bool = False, __orig=candidate, **kwargs):
                    if not sidebar:
                        return None
                    kwargs["sidebar"] = True
                    return __orig(**kwargs)

                setattr(_sidebar_only_nav, wrapper_attr, True)
                setattr(app_mod, name, _sidebar_only_nav)
                nav_fn = _sidebar_only_nav
            break
    if nav_fn is None:
        return
    try:
        nav_fn(sidebar=True)
    except RerunException:
        raise
    except Exception:
        return


def _generate_dummy_workspace(slug: str | None) -> None:
    target = (slug or "dummy").strip() or "dummy"
    try:
        from tools.gen_dummy_kb import main as gen_dummy_main
    except Exception as exc:  # pragma: no cover
        st.sidebar.error(f"Generazione dummy non disponibile: {exc}")
        return
    with st.spinner(f"Genero dataset dummy per '{target}'..."):
        try:
            exit_code = gen_dummy_main(["--slug", target, "--non-interactive"])
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


def _compute_sem_enabled(state: str | None) -> bool:
    """Decide se la tab Semantica è disponibile, in base allo stato client."""
    return _normalize_state(state) in STATE_SEM_READY


def _compute_manage_enabled(state: str | None, slug: str | None) -> bool:
    """Abilita Gestisci cliente da 'inizializzato' in avanti."""
    return _normalize_state(state) in STATE_MANAGE_READY


def _compute_home_enabled(state: str | None, slug: str | None) -> bool:
    """Home è cliccabile in ogni situazione utile (slug presente o stato valido)."""
    normalized = _normalize_state(state)
    if normalized in STATE_MANAGE_READY:
        return True
    return bool((slug or "").strip())


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


def _sidebar_tab_switches(*, home_enabled: bool, manage_enabled: bool, sem_enabled: bool) -> None:
    st.sidebar.markdown("### Sezioni")
    active = st.session_state.get("active_tab", TAB_HOME)
    label_home = "Home [attiva]" if active == TAB_HOME else "Home"
    label_manage = "Gestisci cliente [attiva]" if active == TAB_MANAGE else "Gestisci cliente"
    label_sem = "Semantica [attiva]" if active == TAB_SEM else "Semantica"

    to_home = st.sidebar.button(
        label_home,
        width="stretch",
        disabled=not home_enabled,
        help=None if home_enabled else "Disponibile dopo l'inizializzazione",
        type="primary" if active == TAB_HOME else "secondary",
        key="tab_home_button",
    )
    to_manage = st.sidebar.button(
        label_manage,
        width="stretch",
        disabled=not manage_enabled,
        help=None if manage_enabled else "Disponibile da 'inizializzato'",
        type="primary" if active == TAB_MANAGE else "secondary",
        key="tab_manage_button",
    )
    to_sem = st.sidebar.button(
        label_sem,
        width="stretch",
        disabled=not sem_enabled,
        help=None if sem_enabled else "Disponibile quando lo stato è 'pronto'",
        type="primary" if active == TAB_SEM else "secondary",
        key="tab_sem_button",
    )
    if to_home:
        st.session_state["active_tab"] = TAB_HOME
    if to_manage:
        st.session_state["active_tab"] = TAB_MANAGE
    if to_sem and sem_enabled:
        st.session_state["active_tab"] = TAB_SEM


def _render_tabs_router(active: str, slug: str | None) -> None:
    """Router tab-based. Se i renderer dedicati non esistono, fallback all'app monolitica."""
    logger = _setup_logging()
    try:
        app_mod = importlib.import_module("src.ui.app")
    except Exception as exc:
        logger.info("ui.tabs.module_import_failed", extra={"error": str(exc)})
        raise

    def _call_renderer(name: str, **kwargs) -> bool:
        candidate = getattr(app_mod, name, None)
        if not callable(candidate):
            return False
        try:
            candidate(**kwargs)
        except RerunException:
            raise
        except Exception as exc:
            event = f"ui.tabs.{name}_failed"
            extra = {"error": str(exc), "active_tab": active}
            if "slug" in kwargs and kwargs.get("slug") is not None:
                extra["slug"] = kwargs["slug"]
            logger.info(event, extra=extra)
            raise
        return True

    if active == TAB_HOME and _call_renderer("render_home"):
        return
    if active == TAB_MANAGE and _call_renderer("render_manage", slug=slug, logger=logger):
        return
    if active == TAB_SEM and _call_renderer("render_semantics", slug=slug, logger=logger):
        return

    app_main_candidate = getattr(app_mod, "main", None)
    if callable(app_main_candidate):
        app_main_candidate()
        return

    app_main = importlib.import_module("src.ui.app").main
    app_main()


# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------


def run() -> None:
    _page_config()

    slug = None
    state = None
    try:
        from ui.clients_store import get_state

        try:
            from ui.session import get_current_slug

            slug = get_current_slug()
        except Exception:
            slug = st.session_state.get("current_slug")
        state = (get_state(slug) or "").strip().lower() if slug else None
    except Exception:
        pass

    resolved_slug = _resolve_slug(slug)
    if resolved_slug:
        st.session_state["current_slug"] = resolved_slug
    home_enabled = _compute_home_enabled(state, resolved_slug)
    manage_enabled = _compute_manage_enabled(state, resolved_slug)
    sem_enabled = _compute_sem_enabled(state)

    try:
        _init_tab_state(home_enabled, manage_enabled, sem_enabled)
    except Exception:
        st.session_state["active_tab"] = TAB_HOME

    try:
        _client_header(slug=resolved_slug, state=state)
    except Exception:
        pass

    try:
        _sidebar_brand()
        _sidebar_tab_switches(
            home_enabled=home_enabled,
            manage_enabled=manage_enabled,
            sem_enabled=sem_enabled,
        )
        _sidebar_quick_actions(resolved_slug)
        _sidebar_skiplink_and_quicknav()
    except Exception:
        pass

    try:
        _render_tabs_router(st.session_state.get("active_tab", TAB_HOME), resolved_slug)
    except RerunException:
        raise
    except Exception as e:
        _render_global_error(e)
        try:
            _diagnostics(resolved_slug)
        except Exception:
            pass


if __name__ == "__main__":
    run()
