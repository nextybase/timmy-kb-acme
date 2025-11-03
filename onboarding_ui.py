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

from pipeline.logging_utils import get_structured_logger  # noqa: E402
from ui.config_store import get_skip_preflight, set_skip_preflight  # noqa: E402
from ui.preflight import run_preflight  # noqa: E402
from ui.utils.preflight_once import apply_preflight_once  # noqa: E402
from ui.utils.slug import clear_active_slug  # noqa: E402
from ui.utils.status import status_guard  # noqa: E402
from ui.gating import compute_gates, visible_page_specs  # noqa: E402
from ui.utils.stubs import get_streamlit as _get_streamlit  # noqa: E402
from ui.theme_enhancements import inject_theme_css  # noqa: E402
from ui.utils.branding import get_favicon_path  # noqa: E402

# Router/state helper (fallback soft se non presente)
try:  # noqa: E402
    from ui.utils.route_state import (  # type: ignore
        get_tab,
        set_tab,
        clear_tab,
        get_slug_from_qp,
    )
except Exception:  # pragma: no cover
    def get_tab(default: str = "home") -> str:
        try:
            qp = st.query_params
            val = qp.get("tab")
            if isinstance(val, str) and val.strip():
                return val.strip().lower()
            if isinstance(val, list) and val:
                v = str(val[0]).strip().lower()
                return v or default
        except Exception:
            pass
        return default

    def set_tab(tab: str) -> None:
        try:
            st.query_params["tab"] = (tab or "home")
        except Exception:
            pass

    def clear_tab() -> None:
        try:
            if "tab" in st.query_params:
                del st.query_params["tab"]
        except Exception:
            pass

    def get_slug_from_qp() -> str | None:
        try:
            val = st.query_params.get("slug")
            if isinstance(val, str) and val.strip():
                return val.strip().lower()
            if isinstance(val, list) and val:
                v = str(val[0]).strip().lower()
                return v or None
        except Exception:
            pass
        return None


REPO_ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Onboarding NeXT - Clienti",
    page_icon=str(get_favicon_path(REPO_ROOT)),
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme_css()

# Logger strutturato per eventi di preflight
LOGGER = get_structured_logger("ui.preflight")


def _load_dotenv_best_effort() -> None:
    """Carica .env solo a runtime, preservando l'import-safe della UI."""
    if load_dotenv is None:
        return
    try:
        load_dotenv(override=False)
    except Exception:
        LOGGER.debug("ui.preflight.dotenv_skip", exc_info=True)

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
    """Hydrate defaults for query parameters without forzare ?tab=home nell'URL."""
    try:
        from ui.utils.route_state import get_tab as _get_tab, get_slug_from_qp as _get_slug
    except Exception:
        _ = get_tab("home")
        _ = get_slug_from_qp()
        return
    try:
        _ = _get_tab("home")
        _ = _get_slug()
    except Exception:
        _ = get_tab("home")
        _ = get_slug_from_qp()



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
    try:
        # Azzeramento coerente su query/sessione/persistenza
        clear_active_slug(persist=True, update_query=True)
        clear_tab()
    except Exception:
        pass
    st.stop()

# --------------------------------------------------------------------------------------
# Preflight con feedback + flag persistente "Salta il controllo"
# - Se ui.skip_preflight = True, si bypassa del tutto la sezione.
# - Altrimenti, si mostra l'esito e serve il pulsante "Prosegui".
# --------------------------------------------------------------------------------------
if not st.session_state.get("preflight_ok", False):
    _load_dotenv_best_effort()
    skip_preflight = get_skip_preflight()
    if skip_preflight:
        st.session_state["preflight_ok"] = True
    else:
        box = st.container()
        with box:
            with st.expander("Prerequisiti", expanded=True):
                current_skip = skip_preflight
                new_skip = st.checkbox(
                    "Salta il controllo",
                    value=current_skip,
                    help="Preferenza persistente (config/config.yaml -> ui.skip_preflight).",
                )
                if new_skip != current_skip:
                    try:
                        set_skip_preflight(new_skip)
                        st.toast("Preferenza aggiornata.")
                    except Exception as exc:
                        st.warning(f"Impossibile salvare la preferenza: {exc}")

                once_skip = st.checkbox(
                    "Salta il controllo solo per questa esecuzione",
                    value=False,
                    help="Bypassa il preflight in questa sessione senza modificare la preferenza persistente.",
                )
                if apply_preflight_once(once_skip, st.session_state, LOGGER):
                    st.toast("Preflight saltato per questa run.")
                    st.rerun()

                try:
                    with status_guard(
                        "Controllo prerequisiti…",
                        expanded=True,
                        error_label="Errore nel preflight",
                    ) as s:
                        results, port_busy = run_preflight()

                        # OPENAI/Docker sono opzionali per l'onboarding
                        essential_checks = {"PyMuPDF", "ReportLab", "Google API Client"}
                        essentials_ok = True

                        for name, ok, hint in results:
                            if name in {"OPENAI_API_KEY", "Docker"} and not ok:
                                st.warning(f"[Opzionale] {name} - {hint}")
                            elif ok:
                                st.success(f"[OK] {name}")
                            else:
                                st.error(f"[KO] {name} - {hint}")

                            if name in essential_checks:
                                essentials_ok &= ok

                        if port_busy:
                            st.warning("Porta 4000 occupata: chiudi altre preview HonKit o imposta PORT in .env")

                        if s is not None and hasattr(s, "update"):
                            s.update(label="Controllo completato", state="complete")
                except Exception as exc:
                    st.error(f"Errore nel preflight: {exc}")
                    st.session_state["preflight_ok"] = False
                    st.stop()

                proceed = st.button("Prosegui", type="primary", disabled=not essentials_ok)
                if proceed:
                    st.session_state["preflight_ok"] = True
                    st.rerun()
                else:
                    st.stop()

# --------------------------------------------------------------------------------------
# Definizione pagine (SSoT + gating)
# --------------------------------------------------------------------------------------
_st = _get_streamlit()
_pages_specs = visible_page_specs(compute_gates())
pages = {
    group: [
        _st.Page(spec.path, title=spec.title, url_path=(spec.url_path or None))
        for spec in specs
    ]
    for group, specs in _pages_specs.items()
}

# --------------------------------------------------------------------------------------
# Router nativo: requisito Beta 0
# --------------------------------------------------------------------------------------
navigation = st.navigation(pages, position="top")
navigation.run()
