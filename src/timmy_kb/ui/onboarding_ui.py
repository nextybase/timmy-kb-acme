# SPDX-License-Identifier: GPL-3.0-or-later
# onboarding_ui.py
"""
Onboarding UI entrypoint (Beta 1.0).
- Router nativo Streamlit: st.navigation + st.Page
- Deep-linking via st.query_params (solo default 'tab')
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Any

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.paths import get_repo_root, global_logs_dir
from timmy_kb.versioning import build_env_fingerprint, build_identity
from ui import config_store
from ui.types import StreamlitLike

BOOT_LOG = get_structured_logger("ui.bootstrap")
PREFLIGHT_LOG: logging.Logger = get_structured_logger("ui.preflight")
_ENV_BOOTSTRAPPED = False
_NAV_PAGES_DEBUG_FAILURE_REPORTED = False

# REPO_ROOT_DIR deve puntare alla repo root; WORKSPACE_ROOT_DIR definisce il workspace.


def _init_ui_logging(repo_root: Path) -> None:
    """Inizializza il logger condiviso della UI su `.timmy_kb/logs/ui.log`."""
    from pipeline.logging_utils import get_structured_logger

    log_dir = global_logs_dir(repo_root)
    log_file = log_dir / "ui.log"
    # Propagazione abilitata cosi i logger delle pagine ereditano l'handler file.
    os.environ.setdefault("TIMMY_LOG_PROPAGATE", "1")
    get_structured_logger("ui", log_file=log_file, propagate=True)
    get_structured_logger("ai", log_file=log_file, propagate=True)
    get_structured_logger("ai.responses", log_file=log_file, propagate=True)
    BOOT_LOG.debug("ui.logging.ai_wired")


def _report_nav_pages_debug_failure_once(logger: logging.Logger, exc: Exception) -> None:
    """UI-only: surfaced-once per failure debug logging (no crash, no silent pass)."""
    global _NAV_PAGES_DEBUG_FAILURE_REPORTED
    if _NAV_PAGES_DEBUG_FAILURE_REPORTED:
        return
    _NAV_PAGES_DEBUG_FAILURE_REPORTED = True
    try:
        logger.warning(
            "ui.navigation.pages_log_failed",
            extra={"error_type": type(exc).__name__, "error": repr(exc)},
        )
    except Exception:
        # Ultima difesa: non rompere la UI per failure di logging.
        return


def _lazy_bootstrap(repo_root: Path) -> logging.Logger:
    """Bootstrap logging in modo idempotente (invocato all'avvio UI).

    Ritorna il logger `ui.preflight` da passare alle funzioni interne.
    """
    from pipeline.logging_utils import get_structured_logger

    _init_ui_logging(repo_root)
    return get_structured_logger("ui.preflight")


def _ensure_env_loaded_once() -> None:
    """Carica .env in fase 0, idempotente su rerun."""
    global _ENV_BOOTSTRAPPED
    if _ENV_BOOTSTRAPPED:
        return
    _ENV_BOOTSTRAPPED = True
    from pipeline import env_utils

    # Strict-by-default per la Beta (bassa entropia). Override esplicito: TIMMY_UI_DOTENV_STRICT=0
    raw = os.getenv("TIMMY_UI_DOTENV_STRICT", "1").strip().lower()
    strict = raw not in {"0", "false", "no", "off"}
    env_utils.ensure_dotenv_loaded(strict=strict)
    BOOT_LOG.info(
        "ui.env.dotenv_loaded",
        extra={"strict": strict},
    )


def _render_preflight_header(st_module: StreamlitLike, logger: logging.Logger, *, repo_root: Path) -> None:
    """Logo + titolo centrati per il controllo di sistema (solo schermata preflight)."""
    from ui.utils.branding import get_main_logo_path

    if st_module is None:
        return

    logo_path = None
    try:
        logo_path = get_main_logo_path(repo_root)
    except Exception as exc:
        logger.warning("ui.preflight.logo_resolve_failed", extra={"error": repr(exc)})

    try:
        cols = st_module.columns([1, 2, 1])
    except Exception as exc:
        logger.warning("ui.preflight.columns_failed", extra={"error": repr(exc)})
        cols = None

    target: Any = cols[1] if cols and len(cols) >= 3 else st_module

    def _render(target_st: Any) -> None:
        if logo_path:
            try:
                target_st.image(str(logo_path))
            except Exception as exc:
                logger.warning("ui.preflight.logo_render_failed", extra={"error": repr(exc)})
        try:
            target_st.markdown("### Controllo di sistema")
        except Exception as exc:
            logger.warning("ui.preflight.header_render_failed", extra={"error": repr(exc)})

    try:
        # Alcuni stub non supportano il context manager, quindi degradazione esplicita (UI-only).
        with target:  # type: ignore[assignment]
            _render(target)
    except Exception as exc:
        logger.warning("ui.preflight.header_container_failed", extra={"error": repr(exc)})
        _render(st_module)


_MIN_STREAMLIT_VERSION = (1, 50, 0)


def _parse_version(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in raw.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    return tuple(parts)


def _ensure_streamlit_api(st_module: StreamlitLike) -> None:
    if st_module is None:
        raise RuntimeError("Streamlit non inizializzato")
    version = getattr(st_module, "__version__", "0")
    if (
        _parse_version(version) < _MIN_STREAMLIT_VERSION
        or not hasattr(st_module, "Page")
        or not hasattr(st_module, "navigation")
    ):
        raise RuntimeError(
            "Streamlit 1.50.0 o superiore richiesto per l'interfaccia Beta 1.0. "
            'Aggiorna con `pip install --upgrade "streamlit>=1.50.0"`.'
        )


def _hydrate_query_defaults() -> None:
    """Hydrate defaults for query parameters without forzare ?tab=home nell'URL."""
    try:
        route_state = importlib.import_module("ui.utils.route_state")
        _get_slug = getattr(route_state, "get_slug_from_qp")
        _get_tab = getattr(route_state, "get_tab")
    except Exception as exc:
        PREFLIGHT_LOG.error(
            "ui.route_state.import_failed",
            extra={"error": str(exc)},
        )
        from ui.utils.stubs import get_streamlit

        st = get_streamlit()
        st.error("Router UI non disponibile: impossibile inizializzare i parametri di query.")
        st.stop()
    try:
        _ = _get_tab("home")
        _ = _get_slug()
    except Exception as exc:
        PREFLIGHT_LOG.error(
            "ui.route_state.hydration_failed",
            extra={"error": str(exc)},
        )
        from ui.utils.stubs import get_streamlit

        st = get_streamlit()
        st.error("Errore nel routing UI: impossibile leggere i parametri di query.")
        st.stop()


def _truthy(v: object) -> bool:
    if v is None:
        return False
    if isinstance(v, list):
        v = v[0] if v else ""
    try:
        return str(v).strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    except Exception:
        return False


def _handle_exit_param(
    st_module: StreamlitLike,
    *,
    logger: logging.Logger,
    clear_active_slug,
    clear_tab,
) -> bool:
    """Gestisce il parametro di query ?exit=1 (termina la sessione se attivo)."""
    exit_flag = _truthy(getattr(st_module, "query_params", {}).get("exit"))
    if not exit_flag:
        return False

    st_module.title("Sessione terminata")
    st_module.info("Puoi chiudere questa scheda. Lo slug attivo e' stato azzerato.")
    try:
        clear_active_slug(persist=True, update_query=True)
        clear_tab()
    except Exception as exc:  # pragma: no cover - best effort (non influenza artefatti/gate/ledger/exit code) logging
        logger.warning("ui.slug.reset_failed", extra={"error": str(exc)})
    st_module.stop()
    return True


def _run_preflight_flow(
    st_module: StreamlitLike,
    *,
    logger: logging.Logger,
    run_preflight,
    status_guard,
    repo_root: Path,
) -> None:
    """
    Esegue il preflight, gestendo session_state e rerun/stop.

    - se preflight_ok e' gia' True non fa nulla;
    - altrimenti mostra la UI di controllo, blocca finche' non si preme Prosegui
      o in caso di errore chiama st.stop().
    """
    if st_module.session_state.get("preflight_ok", False):
        return

    if config_store.get_skip_preflight(repo_root=repo_root):
        logger.info(
            "ui.preflight.skipped",
            extra={"reason": "config", "file_path": str(repo_root / "config" / "config.yaml")},
        )
        st_module.session_state["preflight_ok"] = True
        return

    _render_preflight_header(st_module, logger, repo_root=repo_root)
    box = st_module.container()
    with box:
        with st_module.expander("Prerequisiti", expanded=True):
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
                            st_module.warning(f"[Opzionale] {name} - {hint}")
                        elif ok:
                            st_module.success(f"[OK] {name}")
                        else:
                            st_module.error(f"[KO] {name} - {hint}")

                        if name in essential_checks:
                            essentials_ok &= ok

                    if port_busy:
                        st_module.warning("Porta 4000 occupata: chiudi altre preview HonKit o imposta PORT in .env")

                    if s is not None and hasattr(s, "update"):
                        s.update(label="Controllo completato", state="complete")
            except Exception as exc:
                st_module.error(f"Errore nel preflight: {exc}")
                st_module.session_state["preflight_ok"] = False
                st_module.stop()

            proceed = st_module.button("Prosegui", type="primary", disabled=not essentials_ok)
            if proceed:
                st_module.session_state["preflight_ok"] = True
                st_module.rerun()
            else:
                st_module.stop()


def build_navigation(
    *,
    st: StreamlitLike,
    logger: logging.Logger,
    compute_gates,
    visible_page_specs,
    get_streamlit,
    get_active_slug,
    has_normalized_markdown,
) -> None:
    """Costruisce e avvia la navigazione Streamlit (st.navigation + st.Page)."""
    try:
        slug = get_active_slug()
    except Exception:
        slug = None

    # Layout preservato anche se non usiamo direttamente le colonne.
    _ = st.columns([4, 1])

    if slug:
        try:
            has_normalized_markdown(slug)
        except ConfigError as exc:
            # Non blocca la UI, ma non deve essere silenzioso (segnale di stato non pronto).
            logger.info(
                "ui.workspace.normalized_missing_or_invalid",
                extra={"slug": slug, "error": str(exc)},
            )
        except (
            Exception
        ) as exc:  # pragma: no cover - best effort (non influenza artefatti/gate/ledger/exit code) logging
            session_state = getattr(st, "session_state", None)
            once_key = f"_normalized_check_failed_logged::{slug}"
            already_logged = isinstance(session_state, dict) and bool(session_state.get(once_key))
            if not already_logged:
                logger.warning(
                    "ui.workspace.normalized_check_failed",
                    extra={
                        "event": "ui.workspace.normalized_check_failed",
                        "slug": slug,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                if isinstance(session_state, dict):
                    session_state[once_key] = True

    _st = get_streamlit()
    _pages_specs = visible_page_specs(compute_gates())
    pages = {
        group: [_st.Page(spec.path, title=spec.title, url_path=(spec.url_path or None)) for spec in specs]
        for group, specs in _pages_specs.items()
    }

    try:
        logger.debug(
            "ui.navigation.pages",
            extra={
                "pages": {group: [getattr(spec, "path", "") for spec in specs] for group, specs in _pages_specs.items()}
            },
        )
    except Exception as exc:
        _report_nav_pages_debug_failure_once(logger, exc)

    navigation = st.navigation(pages, position="top")
    navigation.run()


def main() -> None:
    _ensure_env_loaded_once()
    try:
        repo_root = get_repo_root()
    except ConfigError as exc:
        BOOT_LOG.error("ui.bootstrap.repo_root_invalid", extra={"error": str(exc)})
        raise

    logger = _lazy_bootstrap(repo_root)

    try:  # noqa: E402
        import streamlit as st  # type: ignore[import]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Streamlit non disponibile: installa le dipendenze UI") from exc

    from ui.gating import compute_gates, visible_page_specs, write_gate_capability_manifest  # noqa: E402
    from ui.preflight import run_preflight  # noqa: E402
    from ui.theme_enhancements import inject_theme_css  # noqa: E402
    from ui.utils import get_active_slug  # noqa: E402
    from ui.utils.branding import get_favicon_path  # noqa: E402
    from ui.utils.slug import clear_active_slug  # noqa: E402
    from ui.utils.status import status_guard  # noqa: E402
    from ui.utils.stubs import get_streamlit as _get_streamlit  # noqa: E402
    from ui.utils.workspace import has_normalized_markdown  # noqa: E402

    global clear_tab, get_slug_from_qp, get_tab, set_tab
    try:  # noqa: E402
        from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab
    except Exception as exc:  # pragma: no cover
        logger.error(
            "ui.preflight.route_state_missing",
            extra={"error": repr(exc)},
        )
        raise RuntimeError("Router UI non disponibile: reinstalla Streamlit/UI") from exc

    st.set_page_config(
        page_title="Onboarding NeXT - Clienti",
        page_icon=str(get_favicon_path(repo_root)),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme_css()

    try:
        _ensure_streamlit_api(st)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    if not st.session_state.get("_startup_logged", False):
        port = os.getenv("PORT") or os.getenv("STREAMLIT_SERVER_PORT") or os.getenv("SERVER_PORT")
        st.session_state["_startup_logged"] = True
        identity = build_identity()
        fp = build_env_fingerprint()
        preflight_skipped = bool(config_store.get_skip_preflight(repo_root=repo_root))
        logger.info(
            "ui.startup",
            extra={
                **identity,
                "streamlit_version": getattr(st, "__version__", "unknown"),
                "port": port,
                "mode": "streamlit",
                "env_fingerprint": fp,
                "preflight_skipped_by_config": preflight_skipped,
            },
        )

    _hydrate_query_defaults()

    # Gestione del parametro di uscita (?exit=1)
    if _handle_exit_param(
        st,
        logger=logger,
        clear_active_slug=clear_active_slug,
        clear_tab=clear_tab,
    ):
        return

    # Flusso di preflight (può impostare preflight_ok e chiamare rerun/stop).
    _run_preflight_flow(
        st_module=st,
        logger=logger,
        run_preflight=run_preflight,
        status_guard=status_guard,
        repo_root=repo_root,
    )

    write_gate_capability_manifest(global_logs_dir(repo_root), env=os.environ)

    # Navigazione principale (st.navigation + st.Page)
    build_navigation(
        st=st,
        logger=logger,
        compute_gates=compute_gates,
        visible_page_specs=visible_page_specs,
        get_streamlit=_get_streamlit,
        get_active_slug=get_active_slug,
        has_normalized_markdown=has_normalized_markdown,
    )


if __name__ == "__main__":
    main()
