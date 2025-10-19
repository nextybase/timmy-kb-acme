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

if load_dotenv:
    try:
        load_dotenv(override=False)
    except Exception:
        pass

# --------------------------------------------------------------------------------------
# Streamlit setup
# --------------------------------------------------------------------------------------
import streamlit as st  # noqa: E402
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
# Preflight con feedback progressivo e memoization in sessione
# --------------------------------------------------------------------------------------
if not st.session_state.get("preflight_ok", False):
    box = st.container()
    with box:
        with st.expander("Prerequisiti", expanded=True):
            progress = st.progress(5, text="Avvio controllo prerequisiti...")
            time.sleep(0.05)
            progress.progress(35, text="Verifica ambiente...")
            try:
                results, port_busy = run_preflight()
            except Exception as exc:
                st.error(f"Errore nel preflight: {exc}")
                st.session_state["preflight_ok"] = False
                st.stop()

            essential_checks = {"PyMuPDF", "ReportLab", "Google API Client", "OPENAI_API_KEY"}
            essentials_ok = True
            progress.progress(60, text="Analisi risultati...")
            for name, ok, hint in results:
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
            st.session_state["preflight_ok"] = essentials_ok

    if st.session_state["preflight_ok"]:
        box.empty()
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
    ],
}

# --------------------------------------------------------------------------------------
# Router nativo: requisito Beta 0
# --------------------------------------------------------------------------------------
navigation = st.navigation(pages, position="top")
navigation.run()
