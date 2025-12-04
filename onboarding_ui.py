# SPDX-License-Identifier: GPL-3.0-or-later
# onboarding_ui.py
"""
Onboarding UI entrypoint (beta 0).
- Router nativo Streamlit: st.navigation + st.Page
- Deep-linking via st.query_params (solo default 'tab')
- Bootstrap di sys.path per importare <repo>/src
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parent
os.environ.pop("REPO_ROOT_DIR", None)

st: Any | None = None


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
        from scripts.smoke_e2e import _add_paths as _repo_add_paths

        try:
            _repo_add_paths()
            return
        except Exception:
            pass
    except Exception:
        pass
    _ensure_repo_src_on_sys_path()


def _init_ui_logging() -> None:
    """Inizializza il logger condiviso della UI su `.timmykb/logs/ui.log`."""
    from pipeline.logging_utils import get_structured_logger
    from pipeline.path_utils import ensure_within_and_resolve

    log_dir = ensure_within_and_resolve(REPO_ROOT, REPO_ROOT / ".timmykb" / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ui.log"
    # Propagazione abilitata cosi i logger delle pagine ereditano l'handler file.
    os.environ.setdefault("TIMMY_LOG_PROPAGATE", "1")
    get_structured_logger("ui", log_file=log_file, propagate=True)


LOGGER: logging.Logger = logging.getLogger("ui.preflight")


def _lazy_bootstrap() -> None:
    """Bootstrap logging in modo idempotente (invocato all'avvio UI)."""
    from pipeline.logging_utils import get_structured_logger

    global LOGGER
    _bootstrap_sys_path()
    _init_ui_logging()
    LOGGER = get_structured_logger("ui.preflight")


def _render_preflight_header() -> None:
    """Logo + titolo centrati per il controllo di sistema (solo schermata preflight)."""
    from ui.utils.branding import get_main_logo_path

    if st is None:
        return

    logo_path = None
    try:
        logo_path = get_main_logo_path(REPO_ROOT)
    except Exception as exc:
        LOGGER.warning("ui.preflight.logo_resolve_failed", extra={"error": repr(exc)})

    try:
        cols = st.columns([1, 2, 1])
    except Exception as exc:
        LOGGER.warning("ui.preflight.columns_failed", extra={"error": repr(exc)})
        cols = None

    target = cols[1] if cols and len(cols) >= 3 else st

    def _render(target_st: Any) -> None:
        if logo_path:
            try:
                target_st.image(str(logo_path))
            except Exception as exc:
                LOGGER.warning("ui.preflight.logo_render_failed", extra={"error": repr(exc)})
        try:
            target_st.markdown("### Controllo di sistema")
        except Exception as exc:
            LOGGER.warning("ui.preflight.header_render_failed", extra={"error": repr(exc)})

    try:
        with target:
            _render(target)
    except Exception as exc:
        LOGGER.warning("ui.preflight.header_container_failed", extra={"error": repr(exc)})
        _render(st)


def _load_dotenv_best_effort() -> None:
    """Carica .env solo a runtime, preservando l'import-safe della UI."""
    if load_dotenv is None:
        return
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        LOGGER.info("ui.preflight.dotenv_missing", extra={"path": str(env_path)})
        return
    try:
        load_dotenv(override=False)
    except Exception as exc:
        LOGGER.warning(
            "ui.preflight.dotenv_error",
            extra={"path": str(env_path), "error": repr(exc)},
        )


_MIN_STREAMLIT_VERSION = (1, 50, 0)


def _parse_version(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in raw.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    return tuple(parts)


def _ensure_streamlit_api() -> None:
    if st is None:
        raise RuntimeError("Streamlit non inizializzato")
    version = getattr(st, "__version__", "0")
    if _parse_version(version) < _MIN_STREAMLIT_VERSION or not hasattr(st, "Page") or not hasattr(st, "navigation"):
        raise RuntimeError(
            "Streamlit 1.50.0 o superiore richiesto per l'interfaccia Beta 0. "
            'Aggiorna con `pip install --upgrade "streamlit>=1.50.0"`.'
        )


def _hydrate_query_defaults() -> None:
    """Hydrate defaults for query parameters without forzare ?tab=home nell'URL."""
    try:
        from ui.utils.route_state import get_slug_from_qp as _get_slug
        from ui.utils.route_state import get_tab as _get_tab
    except Exception:
        def _noop_tab(*_args: object, **_kwargs: object) -> None:
            return None

        def _noop_slug(*_args: object, **_kwargs: object) -> None:
            return None

        _ = _noop_tab("home")
        _ = _noop_slug()
        return
    try:
        _ = _get_tab("home")
        _ = _get_slug()
    except Exception:
        return


def _truthy(v: object) -> bool:
    if v is None:
        return False
    if isinstance(v, list):
        v = v[0] if v else ""
    try:
        return str(v).strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    except Exception:
        return False


def main() -> None:
    global st

    _lazy_bootstrap()

    try:  # noqa: E402
        import streamlit as st  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Streamlit non disponibile: installa le dipendenze UI") from exc

    from ui.config_store import get_skip_preflight, set_skip_preflight  # noqa: E402
    from ui.gating import compute_gates, visible_page_specs  # noqa: E402
    from ui.preflight import run_preflight  # noqa: E402
    from ui.theme_enhancements import inject_theme_css  # noqa: E402
    from ui.utils import get_active_slug  # noqa: E402
    from ui.utils.branding import get_favicon_path  # noqa: E402
    from ui.utils.preflight_once import apply_preflight_once  # noqa: E402
    from ui.utils.slug import clear_active_slug  # noqa: E402
    from ui.utils.status import status_guard  # noqa: E402
    from ui.utils.stubs import get_streamlit as _get_streamlit  # noqa: E402
    from ui.utils.workspace import has_raw_pdfs  # noqa: E402

    global clear_tab, get_slug_from_qp, get_tab, set_tab
    try:  # noqa: E402
        from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab
    except Exception as exc:  # pragma: no cover
        LOGGER.error(
            "ui.preflight.route_state_missing",
            extra={"error": repr(exc)},
        )
        raise RuntimeError("Router UI non disponibile: reinstalla Streamlit/UI") from exc

    st.set_page_config(
        page_title="Onboarding NeXT - Clienti",
        page_icon=str(get_favicon_path(REPO_ROOT)),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme_css()

    try:
        _ensure_streamlit_api()
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    if not st.session_state.get("_startup_logged", False):
        port = os.getenv("PORT") or os.getenv("STREAMLIT_SERVER_PORT") or os.getenv("SERVER_PORT")
        st.session_state["_startup_logged"] = True
        LOGGER.info(
            "ui.startup",
            extra={
                "version": "v1.0-beta",
                "streamlit_version": getattr(st, "__version__", "unknown"),
                "port": port,
                "mode": "streamlit",
            },
        )

    _hydrate_query_defaults()

    if _truthy(getattr(st, "query_params", {}).get("exit")):
        st.title("Sessione terminata")
        st.info("Puoi chiudere questa scheda. Lo slug attivo e' stato azzerato.")
        try:
            clear_active_slug(persist=True, update_query=True)
            clear_tab()
        except Exception as exc:
            LOGGER.warning("ui.slug.reset_failed", extra={"error": str(exc)})
        st.stop()

    skip_preflight = get_skip_preflight()
    if not st.session_state.get("preflight_ok", False):
        _load_dotenv_best_effort()
        if skip_preflight:
            st.session_state["preflight_ok"] = True
        else:
            _render_preflight_header()
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
                            "Controllo prerequisiti...",
                            expanded=True,
                            error_label="Errore nel preflight",
                        ) as s:
                            results, port_busy = run_preflight()

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
    else:
        skip_preflight = get_skip_preflight()

    try:
        slug = get_active_slug()
    except Exception:
        slug = None

    st.columns([4, 1])  # layout preservato anche se non riassegniamo le colonne

    if slug:
        try:
            has_raw_pdfs(slug)
        except Exception as exc:
            LOGGER.warning(
                "ui.workspace.raw_check_failed",
                extra={"event": "ui.workspace.raw_check_failed", "slug": slug, "error": str(exc)},
            )

    _st = _get_streamlit()
    _pages_specs = visible_page_specs(compute_gates())
    pages = {
        group: [_st.Page(spec.path, title=spec.title, url_path=(spec.url_path or None)) for spec in specs]
        for group, specs in _pages_specs.items()
    }

    try:
        LOGGER.info(
            "ui.navigation.pages",
            extra={
                "pages": {
                    group: [getattr(spec, "path", "") for spec in specs] for group, specs in _pages_specs.items()
                }
            },
        )
    except Exception:
        pass

    navigation = st.navigation(pages, position="top")
    navigation.run()


if __name__ == "__main__":
    main()
