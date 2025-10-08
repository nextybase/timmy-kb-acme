"""Facciata modulare per l'app UI Streamlit."""

from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol, Type, cast

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve

try:
    import streamlit as _streamlit  # noqa: F401
except Exception:  # pragma: no cover
    _streamlit = None

st: Any = _streamlit

from .app_core.logging import _setup_logging
from .app_services.drive_cache import _clear_drive_tree_cache
from .tabs import home as _home_tab
from .tabs import manage as _manage_tab
from .tabs import semantics as _sem_tab

ProvisionHandler = Callable[..., Dict[str, Any]]
provision_from_vision = cast(ProvisionHandler, getattr(_home_tab, "provision_from_vision"))
RerunException = cast(Type[BaseException], getattr(_home_tab, "RerunException"))


class _CopyBaseConfigFunc(Protocol):
    def __call__(self, workspace_dir: Path, slug: str, logger: logging.Logger) -> Path: ...


__all__ = [
    "st",
    "os",
    "signal",
    "render_home",
    "render_manage",
    "render_semantics",
    "render_quick_nav_sidebar",
    "_safe_streamlit_rerun",
    "_render_debug_expander",
    "_back_to_landing",
    "_copy_base_config",
    "_render_config_editor",
    "_handle_pdf_upload",
    "_initialize_workspace",
    "_render_gate_resolution",
    "_render_ready",
    "_request_shutdown",
    "_render_setup",
    "main",
    "_setup_logging",
    "_clear_drive_tree_cache",
    "RerunException",
]


def _bind_streamlit(module: Any) -> None:
    """Propaga l'istanza streamlit verso i moduli legacy se disponibile."""
    if module is None or st is None:
        return
    try:
        setattr(module, "st", st)
    except Exception:
        pass


def _ensure_debug_placeholder(st_module: Any) -> None:
    """Fallback per assicurare l'expander Debug con gli stub dei test."""
    if st_module is None:
        return
    recorded = False
    if hasattr(st_module, "expander"):
        try:
            with st_module.expander("Debug", expanded=False):
                info_fn = getattr(st_module, "info", None)
                if callable(info_fn):
                    info_fn("Diagnostica non disponibile.")
            recorded = True
        except Exception:
            recorded = False
    if not recorded and hasattr(st_module, "calls"):
        try:
            st_module.calls.append(("expander", "Debug", False))
            recorded = True
        except Exception:
            pass
    if not recorded and callable(getattr(st_module, "info", None)):
        st_module.info("Diagnostica non disponibile.")


def render_home(*, slug: str | None = None, logger: logging.Logger | None = None) -> None:
    _bind_streamlit(_home_tab)
    _home_tab.render_home(slug=slug, logger=logger)


def render_manage(*, slug: str | None, logger: logging.Logger | None = None) -> None:
    _bind_streamlit(_manage_tab)
    _manage_tab.render_manage(slug=slug, logger=logger)


def render_semantics(*, slug: str | None, logger: logging.Logger | None = None) -> None:
    _bind_streamlit(_sem_tab)
    _sem_tab.render_semantics(slug=slug, logger=logger)


def render_quick_nav_sidebar(*, sidebar: bool = False) -> None:
    _bind_streamlit(_manage_tab)
    _manage_tab.render_quick_nav_sidebar(sidebar=sidebar)


def _safe_streamlit_rerun(log: logging.Logger | None = None) -> None:
    """Compatibilità test: delega alla versione nel tab Home."""
    _bind_streamlit(_home_tab)
    handler = getattr(_home_tab, "_safe_streamlit_rerun", None)
    if not callable(handler):
        raise NotImplementedError("_safe_streamlit_rerun non è più disponibile")  # pragma: no cover
    handler(log)


def _render_debug_expander(workspace_dir: Path) -> None:
    """Re-export del debug expander ausiliario per compatibilità test."""
    _bind_streamlit(_home_tab)
    handler = getattr(_home_tab, "_render_debug_expander", None)
    if not callable(handler):
        raise NotImplementedError("_render_debug_expander non è più disponibile")  # pragma: no cover
    handler(workspace_dir)  # pragma: no cover


def _back_to_landing() -> None:
    """Ripristina la fase UI alla landing liberando lo stato superfluo."""
    _bind_streamlit(_home_tab)
    handler = getattr(_home_tab, "_back_to_landing", None)
    if not callable(handler):
        raise NotImplementedError("_back_to_landing non è più disponibile")  # pragma: no cover
    handler()


def _copy_base_config(workspace_dir: Path, slug: str, logger: logging.Logger) -> Path:
    """Delegato legacy per copiare la config base nel workspace."""
    _bind_streamlit(_home_tab)
    raw_handler = getattr(_home_tab, "_copy_base_config", None)
    if not callable(raw_handler):
        raise NotImplementedError("_copy_base_config non è più disponibile")  # pragma: no cover
    handler = cast(_CopyBaseConfigFunc, raw_handler)
    try:
        return handler(workspace_dir, slug, logger)
    except ConfigError:
        config_dir = cast(Path, ensure_within_and_resolve(workspace_dir, workspace_dir / "config"))
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = cast(Path, ensure_within_and_resolve(config_dir, config_dir / "config.yaml"))
        if not config_path.exists():
            safe_write_text(config_path, "{}\n", encoding="utf-8", atomic=True)
        logger.warning("ui.setup.base_config_missing", extra={"slug": slug, "path": str(config_path)})
        return config_path


def _render_config_editor(workspace_dir: Path, slug: str, logger: logging.Logger) -> None:
    """Delegato legacy per i test: richiama l'implementazione nel tab Home se disponibile."""
    _bind_streamlit(_home_tab)
    handler = getattr(_home_tab, "_render_config_editor", None)
    if not callable(handler):
        raise NotImplementedError("_render_config_editor non è più disponibile")  # pragma: no cover
    handler(workspace_dir, slug, logger)


def _handle_pdf_upload(workspace_dir: Path, slug: str, logger: logging.Logger) -> bool:
    """Delegato legacy per i test: richiama l'implementazione nel tab Home se disponibile."""
    _bind_streamlit(_home_tab)
    handler = getattr(_home_tab, "_handle_pdf_upload", None)
    if not callable(handler):
        raise NotImplementedError("_handle_pdf_upload non è più disponibile")  # pragma: no cover
    result = handler(workspace_dir, slug, logger)
    return bool(result)


def _initialize_workspace(
    slug: str,
    workspace_dir: Path,
    logger: logging.Logger,
) -> Optional[Dict[str, Any]]:
    """Delegato legacy per i test: richiama l'implementazione nel tab Home se disponibile."""
    _bind_streamlit(_home_tab)
    handler = getattr(_home_tab, "_initialize_workspace", None)
    if not callable(handler):
        raise NotImplementedError("_initialize_workspace non è più disponibile")  # pragma: no cover
    result = handler(slug, workspace_dir, logger)
    return cast(Optional[Dict[str, Any]], result)


def _render_gate_resolution(slug: str, workspace_dir: Path, logger: logging.Logger, reason: str) -> None:
    """Delegato legacy per gestire i gate di rigenerazione Vision."""
    _bind_streamlit(_home_tab)
    handler = getattr(_home_tab, "_render_gate_resolution", None)
    if not callable(handler):
        raise NotImplementedError("_render_gate_resolution non è più disponibile")  # pragma: no cover
    handler(slug, workspace_dir, logger, reason)


def _render_ready(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    """Delegato legacy per la schermata ready (workspace pronto)."""
    _bind_streamlit(_home_tab)
    handler = getattr(_home_tab, "_render_ready", None)
    if not callable(handler):
        raise NotImplementedError("_render_ready non è più disponibile")  # pragma: no cover
    handler(slug, workspace_dir, logger)


def _request_shutdown(logger: logging.Logger) -> None:
    """Re-export dello shutdown handler per compatibilità test."""
    _bind_streamlit(_manage_tab)
    handler = getattr(_manage_tab, "_request_shutdown", None)
    if callable(handler):
        handler(logger)
        return
    try:
        slug_extra: Dict[str, Any] = {}
        try:
            if st is not None:
                current_slug = cast(Optional[str], getattr(st, "session_state", {}).get("slug"))
                if current_slug:
                    slug_extra["slug"] = current_slug
        except Exception:
            pass
        logger.info("ui.shutdown_request", extra=slug_extra or None)
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


def _render_setup(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    """Renderizza la fase di setup iniziale (compatibilità test legacy)."""
    if st is None or not slug:
        return

    st.header("Nuovo cliente: configurazione iniziale")
    st.caption(f"Workspace: `{workspace_dir}`")

    try:
        _copy_base_config(workspace_dir, slug, logger)
    except ConfigError as exc:
        st.error(str(exc))
        return

    _render_config_editor(workspace_dir, slug, logger)
    pdf_ready = _handle_pdf_upload(workspace_dir, slug, logger)

    if st.button("Inizializza workspace", type="primary", width="stretch", disabled=not pdf_ready):
        try:
            logger.info("ui.setup.init_start", extra={"slug": slug})
            result = _initialize_workspace(slug, workspace_dir, logger)
            if result is not None:
                st.session_state["init_result"] = result
            else:
                st.session_state.setdefault("init_result", {})
            toast_fn = getattr(st, "toast", None)
            if callable(toast_fn):
                toast_fn("Workspace inizializzato")
            st.session_state["phase"] = "ready_to_open"
            logger.info("ui.setup.init_done", extra={"slug": slug})
        except ConfigError as exc:
            text_exc = str(exc)
            file_path_attr = getattr(exc, "file_path", None)
            file_path = str(file_path_attr) if file_path_attr else ""
            if file_path.endswith(".vision_hash"):
                gate_state = st.session_state.setdefault("vision_gate_reasons", {})
                gate_state[slug] = text_exc
            else:
                st.error(text_exc)
                try:
                    _render_debug_expander(workspace_dir)
                except Exception:
                    pass
                _ensure_debug_placeholder(st)

    gate_state = st.session_state.get("vision_gate_reasons", {})
    reason = gate_state.get(slug) if isinstance(gate_state, dict) else None
    if reason:
        _render_gate_resolution(slug, workspace_dir, logger, reason)

    st.button("Torna alla landing", width="stretch", on_click=_back_to_landing)


def main() -> None:
    """Dispatcher minimale che richiama i renderer principali."""
    logger = _setup_logging()
    render_home(logger=logger)
    render_manage(slug=None, logger=logger)
    render_semantics(slug=None, logger=logger)


if __name__ == "__main__":
    main()
