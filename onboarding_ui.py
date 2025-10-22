# SPDX-License-Identifier: GPL-3.0-or-later
# onboarding_ui.py
"""
Onboarding UI entrypoint (beta 0).
- Router nativo Streamlit: st.navigation + st.Page
- Deep-linking via st.query_params (solo default 'tab')
- Bootstrap di sys.path per importare <repo>/src
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None


# --------------------------------------------------------------------------------------
# Path bootstrap: aggiunge <repo>/src a sys.path il prima possibile
# --------------------------------------------------------------------------------------
def _ensure_repo_src_on_sys_path() -> None:
    repo_root = Path(__file__).parent.resolve()
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _bootstrap_sys_path() -> None:
    try:
        # helper opzionale del repo; se non presente, fallback locale
        from scripts.smoke_e2e import _add_paths as _repo_add_paths  # type: ignore

        try:
            _repo_add_paths()
            return
        except Exception:
            pass
    except Exception:
        pass
    _ensure_repo_src_on_sys_path()


_bootstrap_sys_path()

# --------------------------------------------------------------------------------------
# Streamlit setup
# --------------------------------------------------------------------------------------
import streamlit as st  # noqa: E402

from ui.config_store import get_skip_preflight, set_skip_preflight  # noqa: E402
from ui.preflight import run_preflight  # noqa: E402

st.set_page_config(
    page_title="Onboarding NeXT - Clienti",
    layout="wide",
    initial_sidebar_state="expanded",
)

_MIN_STREAMLIT_VERSION = (1, 50, 0)


def _parse_version(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in raw.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            # stop parsing at first non-numeric segment (e.g. 1.50.0.dev0)
            break
    return tuple(parts)


def _ensure_streamlit_api() -> None:
    version = getattr(st, "__version__", "0")
    if _parse_version(version) < _MIN_STREAMLIT_VERSION or not hasattr(st, "Page") or not hasattr(st, "navigation"):
        raise RuntimeError(
            "Streamlit 1.50.0 o superiore richiesto per l'interfaccia Beta 0. "
            "Aggiorna con `pip install --upgrade streamlit==1.50.*`."
        )


_ensure_streamlit_api()


# Imposta un valore di default della query string per coerenza con deep-linking
def _hydrate_query_defaults() -> None:
    q = st.query_params.to_dict()
    if "tab" not in q:
        st.query_params["tab"] = "home"


_hydrate_query_defaults()


# --------------------------------------------------------------------------------------
# Modalità EXIT: short-circuit prima del preflight
# --------------------------------------------------------------------------------------
def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, list):
        v = v[0] if v else ""
    try:
        return str(v).strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    except Exception:
        return False


if _truthy(getattr(st, "query_params", {}).get("exit")):
    st.title("Sessione terminata")
    st.info("Puoi chiudere questa scheda. Lo slug attivo è stato azzerato.")
    st.stop()

# --------------------------------------------------------------------------------------
# Preflight con feedback + flag persistente "Salta il controllo"
# - Se ui.skip_preflight = True, si bypassa del tutto la sezione.
# - Altrimenti, si mostra l'esito e serve il pulsante "Prosegui".
# --------------------------------------------------------------------------------------
if not st.session_state.get("preflight_ok", False):
    if get_skip_preflight():
        st.session_state["preflight_ok"] = True
    else:
        box = st.container()
        with box:
            with st.expander("Prerequisiti", expanded=True):
                current_skip = get_skip_preflight()
                new_skip = st.checkbox(
                    "Salta il controllo",
                    value=current_skip,
                    help="Preferenza persistente (config/config.yaml → ui.skip_preflight).",
                )
                if new_skip != current_skip:
                    try:
                        set_skip_preflight(new_skip)
                        st.toast("Preferenza aggiornata.")
                    except Exception as exc:
                        st.warning(f"Impossibile salvare la preferenza: {exc}")

                progress = st.progress(5, text="Avvio controllo prerequisiti...")
                time.sleep(0.05)
                progress.progress(35, text="Verifica ambiente...")
                try:
                    results, port_busy = run_preflight()
                except Exception as exc:
                    st.error(f"Errore nel preflight: {exc}")
                    st.session_state["preflight_ok"] = False
                    st.stop()

                essential_checks = {"PyMuPDF", "ReportLab", "Google API Client"}  # OPENAI è opzionale
                essentials_ok = True
                progress.progress(60, text="Analisi risultati...")
                for name, ok, hint in results:
                    if name == "OPENAI_API_KEY" and not ok:
                        st.warning(f"[Opzionale] {name} - {hint}")
                        continue
                    if name == "Docker" and not ok:
                        st.warning(f"[Opzionale] {name} - {hint}")
                        continue
                    if ok:
                        st.success(f"[OK] {name}")
                    else:
                        st.error(f"[KO] {name} - {hint}")
                    if name in essential_checks:
                        essentials_ok &= ok

                if port_busy:
                    st.warning("Porta 4000 occupata: chiudi altre preview HonKit o imposta PORT in .env")

                progress.progress(100, text="Controllo completato")
                proceed = st.button("Prosegui", type="primary", disabled=not essentials_ok)
                if proceed:
                    st.session_state["preflight_ok"] = True
                    st.rerun()
                else:
                    st.stop()

# --------------------------------------------------------------------------------------
# Definizione pagine
# L'ordine definisce la pagina "default" (qui: Home)
# --------------------------------------------------------------------------------------
pages = {
    "Onboarding": [
        st.Page("src/ui/pages/home.py", title="Home"),
        st.Page("src/ui/pages/new_client.py", title="Nuovo cliente", url_path="new"),
        st.Page("src/ui/pages/manage.py", title="Gestisci cliente", url_path="manage"),
        st.Page("src/ui/pages/semantics.py", title="Semantica", url_path="semantics"),
    ],
    "Tools": [
        st.Page("src/ui/pages/admin.py", title="Admin", url_path="admin"),
        st.Page("src/ui/pages/settings.py", title="Settings", url_path="settings"),
        st.Page("src/ui/pages/preview.py", title="Docker Preview", url_path="preview"),
        st.Page("src/ui/pages/cleanup.py", title="Cleanup", url_path="cleanup"),
        st.Page("src/ui/pages/diagnostics.py", title="Diagnostica", url_path="diagnostics"),
        st.Page("src/ui/pages/guida_ui.py", title="Guida UI", url_path="guida"),
        st.Page("src/ui/pages/tools_check.py", title="Healthcheck", url_path="check"),
    ],
}

# --------------------------------------------------------------------------------------
# Router nativo: requisito Beta 0
# --------------------------------------------------------------------------------------
navigation = st.navigation(pages, position="top")
navigation.run()
