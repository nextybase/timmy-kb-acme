# SPDX-License-Identifier: GPL-3.0-or-later
# onboarding_ui.py
"""
Onboarding UI entrypoint (Beta 1.0).
- Router nativo Streamlit: st.navigation + st.Page
- Deep-linking via st.query_params (solo default 'tab')
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.paths import get_repo_root, global_logs_dir
from timmy_kb.versioning import build_identity
from ui.types import StreamlitLike

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

LOGGER = get_structured_logger("ui.bootstrap")

try:
    REPO_ROOT = get_repo_root()
except ConfigError as exc:
    LOGGER.error("ui.bootstrap.repo_root_missing", extra={"error": str(exc)})
    raise

# Non vogliamo che REPO_ROOT_DIR da env interferisca col SSoT.
os.environ.pop("REPO_ROOT_DIR", None)


def _init_ui_logging() -> None:
    """Inizializza il logger condiviso della UI su `.timmy_kb/logs/ui.log`."""
    from pipeline.logging_utils import get_structured_logger

    log_dir = global_logs_dir(REPO_ROOT)
    log_file = log_dir / "ui.log"
    # Propagazione abilitata cosi i logger delle pagine ereditano l'handler file.
    os.environ.setdefault("TIMMY_LOG_PROPAGATE", "1")
    get_structured_logger("ui", log_file=log_file, propagate=True)


LOGGER: logging.Logger = get_structured_logger("ui.preflight")


def _lazy_bootstrap() -> logging.Logger:
    """Bootstrap logging in modo idempotente (invocato all'avvio UI).

    Ritorna il logger `ui.preflight` da passare alle funzioni interne.
    """
    from pipeline.logging_utils import get_structured_logger

    _init_ui_logging()
    return get_structured_logger("ui.preflight")


def _render_preflight_header(st_module: StreamlitLike, logger: logging.Logger) -> None:
    """Logo + titolo centrati per il controllo di sistema (solo schermata preflight)."""
    from ui.utils.branding import get_main_logo_path

    if st_module is None:
        return

    logo_path = None
    try:
        logo_path = get_main_logo_path(REPO_ROOT)
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
        # Alcuni stub non supportano il context manager, quindi fallback esplicito.
        with target:  # type: ignore[assignment]
            _render(target)
    except Exception as exc:
        logger.warning("ui.preflight.header_container_failed", extra={"error": repr(exc)})
        _render(st_module)


def _load_dotenv_best_effort(logger: logging.Logger) -> None:
    """Carica .env solo a runtime, preservando l'import-safe della UI."""
    if load_dotenv is None:
        return
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        logger.info("ui.preflight.dotenv_missing", extra={"path": str(env_path)})
        return
    try:
        load_dotenv(override=False)
    except Exception as exc:
        logger.warning(
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
    except Exception as exc:  # pragma: no cover - best effort logging
        logger.warning("ui.slug.reset_failed", extra={"error": str(exc)})
    st_module.stop()
    return True


def _run_preflight_flow(
    st_module: StreamlitLike,
    *,
    logger: logging.Logger,
    get_skip_preflight,
    set_skip_preflight,
    apply_preflight_once,
    run_preflight,
    status_guard,
) -> None:
    """
    Esegue (o salta) il preflight, gestendo session_state e rerun/stop.

    Mantiene la stessa semantica del blocco precedente in main:
    - se preflight_ok è già True → non fa nulla;
    - se skip_preflight è attivo → setta preflight_ok=True e prosegue;
    - altrimenti mostra la UI di controllo, blocca finché non si preme Prosegui
      o in caso di errore chiama st.stop().
    """
    skip_preflight = get_skip_preflight()

    if st_module.session_state.get("preflight_ok", False):
        return

    _load_dotenv_best_effort(logger)

    if skip_preflight:
        st_module.session_state["preflight_ok"] = True
        return

    _render_preflight_header(st_module, logger)
    box = st_module.container()
    with box:
        with st_module.expander("Prerequisiti", expanded=True):
            current_skip = skip_preflight
            new_skip = st_module.checkbox(
                "Salta il controllo",
                value=current_skip,
                help="Preferenza persistente (config/config.yaml -> ui.skip_preflight).",
            )
            if new_skip != current_skip:
                try:
                    set_skip_preflight(new_skip)
                    st_module.toast("Preferenza aggiornata.")
                except Exception as exc:  # pragma: no cover - UI feedback best effort
                    st_module.warning(f"Impossibile salvare la preferenza: {exc}")

            once_skip = st_module.checkbox(
                "Salta il controllo solo per questa esecuzione",
                value=False,
                help="Bypassa il preflight in questa sessione senza modificare la preferenza persistente.",
            )
            if apply_preflight_once(once_skip, st_module.session_state, logger):
                st_module.toast("Preflight saltato per questa run.")
                st_module.rerun()

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
    has_raw_pdfs,
) -> None:
    """Costruisce e avvia la navigazione Streamlit (st.navigation + st.Page)."""
    try:
        slug = get_active_slug()
    except Exception:
        slug = None

    # Layout preservato anche se non usiamo direttamente le colonne.
    st.columns([4, 1])

    if slug:
        try:
            has_raw_pdfs(slug)
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.warning(
                "ui.workspace.raw_check_failed",
                extra={"event": "ui.workspace.raw_check_failed", "slug": slug, "error": str(exc)},
            )

    _st = get_streamlit()
    _pages_specs = visible_page_specs(compute_gates())
    pages = {
        group: [_st.Page(spec.path, title=spec.title, url_path=(spec.url_path or None)) for spec in specs]
        for group, specs in _pages_specs.items()
    }

    try:
        logger.info(
            "ui.navigation.pages",
            extra={
                "pages": {group: [getattr(spec, "path", "") for spec in specs] for group, specs in _pages_specs.items()}
            },
        )
    except Exception:
        pass

    navigation = st.navigation(pages, position="top")
    navigation.run()


def main() -> None:
    logger = _lazy_bootstrap()

    try:  # noqa: E402
        import streamlit as st  # type: ignore[import]
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
        logger.error(
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
        _ensure_streamlit_api(st)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    if not st.session_state.get("_startup_logged", False):
        port = os.getenv("PORT") or os.getenv("STREAMLIT_SERVER_PORT") or os.getenv("SERVER_PORT")
        st.session_state["_startup_logged"] = True
        identity = build_identity()
        logger.info(
            "ui.startup",
            extra={
                **identity,
                "streamlit_version": getattr(st, "__version__", "unknown"),
                "port": port,
                "mode": "streamlit",
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
        get_skip_preflight=get_skip_preflight,
        set_skip_preflight=set_skip_preflight,
        apply_preflight_once=apply_preflight_once,
        run_preflight=run_preflight,
        status_guard=status_guard,
    )

    # Navigazione principale (st.navigation + st.Page)
    build_navigation(
        st=st,
        logger=logger,
        compute_gates=compute_gates,
        visible_page_specs=visible_page_specs,
        get_streamlit=_get_streamlit,
        get_active_slug=get_active_slug,
        has_raw_pdfs=has_raw_pdfs,
    )


if __name__ == "__main__":
    main()
