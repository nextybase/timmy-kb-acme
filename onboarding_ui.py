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

import os
import sys
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException
from src.ui.app import _setup_logging


ICON_REFRESH = "\U0001F504"


STATE_MANAGE_READY = {"inizializzato", "pronto", "arricchito", "finito"}
STATE_SEM_READY = {"pronto", "arricchito", "finito"}



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
        from scripts.smoke_e2e import _add_paths as _repo_add_paths  # type: ignore

        _repo_add_paths()
    except Exception:
        # Fallback robusto
        _ensure_repo_src_on_sys_path()


# Esegui bootstrap path il prima possibile
_bootstrap_sys_path()


# ------------------------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------------------------

def _normalize_state(state: str | None) -> str:
    return (state or "").strip().lower()

def _page_config() -> None:
    # UI: page config deve essere la prima chiamata Streamlit
    st.set_page_config(
        page_title="Onboarding NeXT - Clienti",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    # UI: skip-links per accessibilità tastiera
    st.markdown(
        "<a href='#main' class='sr-only-focusable'>Salta al contenuto principale</a>",
        unsafe_allow_html=True,
    )


def _render_global_error(e: Exception) -> None:
    # UI: messaggio breve + toast non bloccante
    try:
        st.toast("Si è verificato un errore. Dettagli nei log/expander.", icon="⚠️")
    except Exception:
        pass
    st.error("Errore. Apri i dettagli tecnici per maggiori informazioni.")
    with st.expander("Dettagli tecnici", expanded=False):
        st.exception(e)


# ----------------------------------------------------------------------
# UI add-ons (solo presentazione, nessun side-effect di business logic)
# ----------------------------------------------------------------------

def _client_header(*, slug: str | None, state: str | None) -> None:
    """Compact header con stato cliente + link rapidi. UI-only, idempotent."""
    st.markdown("<div id='main'></div>", unsafe_allow_html=True)  # anchor per skip-link
    if not slug:
        st.info("Nessun cliente selezionato. Usa **Nuovo Cliente** o **Gestisci cliente** dalla landing.")
        return

    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
    with col1:
        st.subheader(f"Cliente: `{slug}`")
    with col2:
        badge = (state or "sconosciuto").lower()
        st.metric("Stato", badge)
    with col3:
        if st.button("Apri workspace", help="Apri la cartella locale del cliente (path in Diagnostica)"):
            st.toast("Apri workspace: copia/incolla il percorso dalla sezione Diagnostica.", icon="📂")
    with col4:
        # Link pubblico alla guida del repo (resta valido anche fuori preview)
        st.link_button(
            "Guida UI",
            "https://github.com/nextybase/timmy-kb-acme/blob/main/docs/guida_ui.md",
        )


def _status_bar():
    """Area di stato leggera. Usare insieme a st.status nei flussi lunghi."""
    placeholder = st.empty()

    def update(msg: str, icon: str = "⏳"):
        try:
            placeholder.info(f"{icon} {msg}")
        except Exception:
            pass

    def clear():
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
            from pipeline.context import ClientContext  # type: ignore
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
                        buf = latest.read_bytes()[-4000:]
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


def _sidebar_quick_actions(slug: str | None) -> None:
    st.sidebar.markdown("### Azioni rapide")
    if st.sidebar.button("Home", help="Torna alla schermata principale.", use_container_width=True):
        st.session_state["active_tab"] = TAB_HOME
    if st.sidebar.button("Aggiorna elenco Drive", use_container_width=True):
        st.session_state.pop("drive_cache_buster", None)
        st.toast("Richiesta aggiornamento Drive inviata.", icon=ICON_REFRESH)
    if st.sidebar.button(
        "Genera dummy",
        help="Crea il workspace di esempio per testare il flusso.",
        use_container_width=True,
    ):
        _generate_dummy_workspace(slug)
    if st.sidebar.button("Esci", type="primary", help="Chiudi l'app.", use_container_width=True):
        _request_shutdown_safe()
    st.sidebar.markdown("---")

# ------------------------------------------------------------------------------
# Tabs helpers / gating
# ------------------------------------------------------------------------------
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
        from src.ui.app import _request_shutdown  # type: ignore
    except Exception as exc:  # pragma: no cover
        st.sidebar.error(f"Chiusura non disponibile: {exc}")
        return
    try:
        _request_shutdown(_setup_logging())  # type: ignore[arg-type]
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
    normalized = _normalize_state(state)
    if normalized in STATE_MANAGE_READY:
        return True
    return bool((slug or "").strip())


def _compute_home_enabled(state: str | None, slug: str | None) -> bool:
    """Home è cliccabile in ogni situazione utile (slug presente o stato valido)."""
    normalized = _normalize_state(state)
    if normalized in STATE_MANAGE_READY:
        return True
    return bool((slug or "").strip())


def _init_tab_state(home_enabled: bool, manage_enabled: bool, sem_enabled: bool) -> None:
    """Inizializza/riconcilia la tab attiva in sessione, sempre chiamata."""
    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = TAB_HOME
        if manage_enabled:
            st.session_state["active_tab"] = TAB_MANAGE
        return
    if not home_enabled:
        st.session_state["active_tab"] = TAB_HOME
        return
    active = st.session_state.get("active_tab", TAB_HOME)
    if active == TAB_HOME and manage_enabled:
        st.session_state["active_tab"] = TAB_MANAGE
        return
    if active == TAB_MANAGE and not manage_enabled:
        st.session_state["active_tab"] = TAB_HOME
    elif active == TAB_SEM and not sem_enabled:
        st.session_state["active_tab"] = TAB_HOME

def _sidebar_tab_switches(
    *, home_enabled: bool, manage_enabled: bool, sem_enabled: bool
) -> None:
    st.sidebar.markdown("### Sezioni")
    active = st.session_state.get("active_tab", TAB_HOME)
    label_home = "Home [attiva]" if active == TAB_HOME else "Home"
    label_manage = "Gestisci cliente [attiva]" if active == TAB_MANAGE else "Gestisci cliente"
    label_sem = "Semantica [attiva]" if active == TAB_SEM else "Semantica"

    to_home = st.sidebar.button(
        label_home,
        use_container_width=True,
        disabled=not home_enabled,
        help=None if home_enabled else "Disponibile dopo l'inizializzazione",
    )
    to_manage = st.sidebar.button(
        label_manage,
        use_container_width=True,
        disabled=not manage_enabled,
        help=None if manage_enabled else "Disponibile da 'inizializzato'",
    )
    to_sem = st.sidebar.button(
        label_sem,
        use_container_width=True,
        disabled=not sem_enabled,
        help=None if sem_enabled else "Disponibile quando lo stato è 'pronto'",
    )
    if to_home:
        st.session_state["active_tab"] = TAB_HOME
    if to_manage:
        st.session_state["active_tab"] = TAB_MANAGE
    if to_sem and sem_enabled:
        st.session_state["active_tab"] = TAB_SEM

def _render_tabs_router(active: str, slug: str | None) -> None:
    """Router tab-based. Se i renderer dedicati non esistono, fallback all'app monolitica."""
    try:
        from src.ui import app as app_mod  # type: ignore
    except Exception:
        app_mod = None
    else:
        if active == TAB_HOME:
            try:
                render_home = getattr(app_mod, "render_home", None)
                if callable(render_home):
                    render_home()
                    return
            except RerunException:
                raise
            except Exception:
                pass
        if active == TAB_MANAGE:
            try:
                render_manage = getattr(app_mod, "render_manage", None)
                if callable(render_manage):
                    render_manage(slug=slug, logger=_setup_logging())
                    return
            except RerunException:
                raise
            except Exception:
                pass
        if active == TAB_SEM:
            try:
                render_semantics = getattr(app_mod, "render_semantics", None)
                if callable(render_semantics):
                    render_semantics(slug=slug, logger=_setup_logging())
                    return
            except RerunException:
                raise
            except Exception:
                pass

    from src.ui.app import main as app_main  # type: ignore
    app_main()

# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------

def run() -> None:
    _page_config()

    slug = None
    state = None
    try:
        from ui.clients_store import get_state  # type: ignore
        try:
            from ui.session import get_current_slug  # type: ignore
            slug = get_current_slug()
        except Exception:
            slug = st.session_state.get("current_slug")
        state = (get_state(slug) or "").strip().lower() if slug else None
    except Exception:
        pass

    home_enabled = _compute_home_enabled(state, slug)
    manage_enabled = _compute_manage_enabled(state, slug)
    sem_enabled = _compute_sem_enabled(state)

    try:
        _init_tab_state(home_enabled, manage_enabled, sem_enabled)
    except Exception:
        st.session_state["active_tab"] = TAB_HOME

    try:
        _client_header(slug=slug, state=state)
        _sidebar_quick_actions(slug)
    except Exception:
        pass

    try:
        _sidebar_tab_switches(
            home_enabled=home_enabled,
            manage_enabled=manage_enabled,
            sem_enabled=sem_enabled,
        )
    except Exception:
        pass

    try:
        _render_tabs_router(st.session_state.get("active_tab", TAB_HOME), slug)
    except RerunException:
        raise
    except Exception as e:
        _render_global_error(e)
        try:
            _diagnostics(slug)
        except Exception:
            pass


if __name__ == "__main__":
    run()
