"""Helper per la composizione del layout Streamlit."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Tuple

from ui.utils.branding import render_brand_header, render_sidebar_brand

__all__ = [
    "render_client_header",
    "build_status_bar",
    "render_sidebar_branding",
    "render_sidebar_quick_actions",
    "render_sidebar_skiplink_and_quicknav",
    "render_sidebar_tab_switches",
]


def render_client_header(
    *,
    st_module: Any,
    repo_root: Path,
    slug: str | None,
    state: str | None,
) -> None:
    """Renderizza l'header principale con il branding del progetto."""
    _ = state
    subtitle = None
    render_brand_header(
        st_module=st_module,
        repo_root=repo_root,
        subtitle=subtitle,
        include_anchor=True,
        show_logo=False,
    )
    if not slug:
        st_module.info("Nessun cliente selezionato. Usa **Nuovo Cliente** o **Gestisci cliente** dalla landing.")


def build_status_bar(st_module: Any) -> Tuple[Callable[[str, str], None], Callable[[], None]]:
    """Restituisce updater/clearer per una status bar leggera."""
    placeholder = st_module.empty()

    def update(msg: str, icon: str = "??") -> None:
        try:
            placeholder.info(f"{icon} {msg}")
        except Exception:
            pass

    def clear() -> None:
        placeholder.empty()

    return update, clear


def render_sidebar_branding(*, st_module: Any, repo_root: Path) -> None:
    """Mostra il brand/logo tematico nella sidebar."""
    try:
        render_sidebar_brand(st_module.sidebar, repo_root)
    except Exception:
        pass


def render_sidebar_quick_actions(
    *,
    st_module: Any,
    slug: str | None,
    icon_refresh: str,
    refresh_callback: Callable[[], Tuple[bool, str | None]],
    generate_dummy_callback: Callable[[], None],
    request_shutdown_callback: Callable[[], None],
    logger: logging.Logger,
) -> None:
    """Sidebar con azioni rapide (refresh Drive, dummy workspace, shutdown)."""
    sidebar = st_module.sidebar
    sidebar.markdown("### Azioni rapide")
    sidebar.link_button("Guida UI", "https://github.com/nextybase/timmy-kb-acme/blob/main/docs/guida_ui.md")

    if sidebar.button(
        "Aggiorna elenco Drive",
        key="sidebar_refresh_drive",
        width="stretch",
    ):
        success, warning_msg = refresh_callback()
        if success:
            try:
                st_module.toast("Richiesta aggiornamento Drive inviata.", icon=icon_refresh)
            except Exception:
                pass
        else:
            sidebar.warning(warning_msg or "Cache Drive non disponibile.")

    if sidebar.button(
        "Genera dummy",
        key="sidebar_dummy_btn",
        width="stretch",
        help="Crea il workspace di esempio per testare il flusso.",
    ):
        logger.info(
            "ui.sidebar.generate_dummy_requested",
            extra={"slug": slug},
        )
        generate_dummy_callback()
        # TODO: deduplicare la logica di generazione dummy fra UI e CLI (stesse opzioni/spinner).

    if sidebar.button("Esci", type="primary", width="stretch", help="Chiudi l'app"):
        logger.info("ui.sidebar.shutdown_requested", extra={"slug": slug})
        request_shutdown_callback()

    sidebar.markdown("---")


def render_sidebar_skiplink_and_quicknav(*, st_module: Any) -> None:
    """Inserisce skip-link e quick navigation se disponibile."""
    st_module.sidebar.markdown("<small><a href='#main' tabindex='0'>Main</a></small>", unsafe_allow_html=True)

    try:
        app_mod = importlib.import_module("src.ui.app")
    except Exception:
        return

    for name in ("render_quick_nav_sidebar", "render_quick_nav", "render_quick_navigation", "quick_nav"):
        candidate = getattr(app_mod, name, None)
        if not callable(candidate):
            continue
        try:
            candidate(sidebar=True)
        except TypeError:
            try:
                candidate()
            except Exception:
                return
        except Exception:
            return
        return
    # TODO: centralizzare la ricerca dei nomi quick-nav per evitare this loop replicato altrove.


def render_sidebar_tab_switches(
    *,
    st_module: Any,
    active_tab_key: str,
    tab_home: str,
    tab_manage: str,
    tab_sem: str,
    home_enabled: bool,
    manage_enabled: bool,
    sem_enabled: bool,
) -> None:
    """Renderizza la sezione di switch tab nella sidebar."""
    sidebar = st_module.sidebar
    sidebar.markdown("### Sezioni")
    active = st_module.session_state.get(active_tab_key, tab_home)
    label_home = "Home [attiva]" if active == tab_home else "Home"
    label_manage = "Gestisci cliente [attiva]" if active == tab_manage else "Gestisci cliente"
    label_sem = "Semantica [attiva]" if active == tab_sem else "Semantica"

    to_home = sidebar.button(
        label_home,
        width="stretch",
        disabled=not home_enabled,
        help=None if home_enabled else "Disponibile dopo l'inizializzazione",
        type="primary" if active == tab_home else "secondary",
        key="tab_home_button",
    )
    to_manage = sidebar.button(
        label_manage,
        width="stretch",
        disabled=not manage_enabled,
        help=None if manage_enabled else "Disponibile da 'inizializzato'",
        type="primary" if active == tab_manage else "secondary",
        key="tab_manage_button",
    )
    to_sem = sidebar.button(
        label_sem,
        width="stretch",
        disabled=not sem_enabled,
        help=None if sem_enabled else "Disponibile quando lo stato è 'pronto' e raw/ contiene PDF",
        type="primary" if active == tab_sem else "secondary",
        key="tab_sem_button",
    )

    if to_home:
        st_module.session_state[active_tab_key] = tab_home
    if to_manage:
        st_module.session_state[active_tab_key] = tab_manage
    if to_sem and sem_enabled:
        st_module.session_state[active_tab_key] = tab_sem
