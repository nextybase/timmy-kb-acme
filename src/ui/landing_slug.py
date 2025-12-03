# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/landing_slug.py
from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Literal, Optional, Tuple, cast

from pipeline.env_utils import get_bool
from pipeline.exceptions import ConfigError, InvalidSlug
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe, validate_slug
from pre_onboarding import ensure_local_workspace_for_ui
from ui.utils.context_cache import get_client_context
from ui.utils.workspace import workspace_root

from .services import vision_provision as vision_services
from .utils.branding import render_brand_header

if TYPE_CHECKING:
    from pipeline.context import ClientContext
else:  # pragma: no cover
    ClientContext = Any

st: Any | None
try:  # preferisce runtime soft-fail per import opzionali
    import streamlit as _st

    st = _st
except Exception:  # pragma: no cover
    st = None


def _safe_rerun() -> None:
    """Richiede un rerun Streamlit se disponibile, senza dipendere da src.ui.app."""
    if st is None:
        return
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        try:
            rerun_fn()
        except Exception:
            # In alcune versioni Streamlit puÃ² sollevare eccezioni interne di rerun: ignoriamo.
            pass


REPO_ROOT = Path(__file__).resolve().parents[2]

UI_STATE_PREFIX = "ui."


def _ui_key(name: str) -> str:
    return f"{UI_STATE_PREFIX}{name}"


def _state_get(name: str, default: Any | None = None) -> Any | None:
    if st is None:
        return default
    full_key = _ui_key(name)
    if full_key in st.session_state:
        return st.session_state.get(full_key, default)
    return st.session_state.get(name, default)


def _state_set(name: str, value: Any) -> None:
    if st is None:
        return
    full_key = _ui_key(name)
    st.session_state[full_key] = value
    st.session_state[name] = value


def _state_pop(name: str) -> Any:
    if st is None:
        return None
    full_key = _ui_key(name)
    value = st.session_state.pop(full_key, None)
    st.session_state.pop(name, None)
    return value


class _NullForm:
    def __enter__(self) -> "_NullForm":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        return False


def _safe_form(name: str, clear_on_submit: bool = False) -> ContextManager[Any]:
    if st is None:
        return cast(ContextManager[Any], _NullForm())
    form_fn = getattr(st, "form", None)
    if callable(form_fn):
        try:
            return cast(ContextManager[Any], form_fn(name, clear_on_submit=clear_on_submit))
        except TypeError as exc:
            if "clear_on_submit" not in str(exc):
                raise
            return cast(ContextManager[Any], form_fn(name))
    return cast(ContextManager[Any], _NullForm())


def _safe_form_submit(label: str, **kwargs: Any) -> bool:
    if st is None:
        return False
    submit_fn = getattr(st, "form_submit_button", None)
    if callable(submit_fn):
        try:
            result = submit_fn(label, **kwargs)
        except TypeError as exc:
            message = str(exc)
            if any(key in message for key in kwargs.keys()):
                result = submit_fn(label)
            else:
                raise
        return bool(result)
    return bool(getattr(st, "button", lambda *a, **k: False)(label, **kwargs))


CLIENT_CONTEXT_ERROR_MSG = (
    "ClientContext non disponibile. Esegui pre_onboarding.ensure_local_workspace_for_ui o imposta REPO_ROOT_DIR."
)


def _reset_to_landing() -> None:
    """Reimposta lo stato UI e torna alla landing (slug vuoto)."""
    if st is None:
        return
    preserve = {"phase", _ui_key("phase")}
    for key in list(st.session_state.keys()):
        if key not in preserve:
            st.session_state.pop(key, None)
    _state_set("slug", "")
    try:
        _safe_rerun()
    except Exception:
        pass


def _workspace_dir_for(slug: str) -> Path:
    return cast(Path, workspace_root(slug))


def _request_shutdown(logger: Optional[logging.Logger]) -> None:
    try:
        (logger or get_structured_logger("ui.landing_slug")).info("ui.shutdown_request")
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


def _base_dir_for(slug: str) -> Path:
    try:
        ctx = get_client_context(slug, interactive=False, require_env=False)
    except Exception as exc:
        raise RuntimeError(CLIENT_CONTEXT_ERROR_MSG) from exc

    base = getattr(ctx, "base_dir", None)
    if isinstance(base, Path):
        return base

    raw_dir = getattr(ctx, "raw_dir", None)
    if isinstance(raw_dir, Path):
        return raw_dir.parent

    raise RuntimeError(CLIENT_CONTEXT_ERROR_MSG)


def _st_notify(level: str, message: str) -> None:
    """Invoca st.<level> se disponibile, altrimenti fallback a warning/info.

    Compatibile con stub/dummy usati nei test dove `st.error`/`st.warning`
    possono non esistere. Non solleva eccezioni.
    """
    if st is None:
        return
    # Prova il livello richiesto, poi degrada a warning/info
    for name in (level, "warning", "info"):
        fn = getattr(st, name, None)
        if callable(fn):
            try:
                fn(message)
                break
            except Exception:
                continue


def _enter_existing_workspace(slug: str, fallback_name: str) -> Tuple[bool, str, str]:
    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")
    client_name: str = fallback_name or slug
    try:
        ctx = get_client_context(slug, interactive=False, require_env=False)
        from pipeline.config_utils import get_client_config

        cfg = get_client_config(ctx) or {}
        client_name = str(cfg.get("client_name") or slug)
    except Exception:  # pragma: no cover
        client_name = fallback_name or slug

    _state_set("slug", slug)
    _state_set("client_name", client_name)
    _state_set("client_locked", True)
    _state_set("active_section", "Configurazione")
    _state_pop("vision_workflow")
    try:
        _safe_rerun()
    except Exception:  # pragma: no cover
        pass
    return True, slug, client_name


# Legacy helper mantenuto per compatibilitÃ  con i test esistenti
def _render_logo() -> None:
    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        include_anchor=True,
        subtitle="Verifica slug cliente per avviare l'onboarding.",
        show_logo=False,
    )


def _normalize_slug_value(value: str | None) -> str:
    return (value or "").strip()


def _validate_candidate_slug(candidate: str) -> tuple[bool, Optional[str]]:
    if not candidate:
        return False, "Inserisci uno slug."
    try:
        validate_slug(candidate)
    except InvalidSlug:
        return False, "Slug non valido. Usa solo minuscole, numeri e trattini."
    return True, None


def render_header_form(slug_state: str, log: Optional[logging.Logger]) -> tuple[str, bool]:
    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")
    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        include_anchor=True,
        subtitle="Verifica slug cliente per avviare l'onboarding.",
    )
    spacer_html = "<div style='height: 2vh'></div>"
    html_renderer = getattr(st, "html", None)
    if callable(html_renderer):
        html_renderer(spacer_html)
    else:
        safe_write = getattr(st, "write", None)
        if callable(safe_write):
            safe_write("")

    _, col_form, _ = st.columns([1, 2, 1])
    with col_form:
        with _safe_form("ls_slug_form", clear_on_submit=False):
            slug_input = st.text_input("Slug cliente", value=slug_state, key="ls_slug", placeholder="es. acme")
            verify_clicked = _safe_form_submit("Verifica cliente", type="primary")
        if get_bool("UI_ALLOW_EXIT", default=False):
            st.button("Esci", key="ls_exit", on_click=lambda: _request_shutdown(log), width="stretch")
    return slug_input, verify_clicked


def handle_verify_workflow(
    slug_state: str,
    slug_input: str,
    verify_clicked: bool,
    vision_state: Optional[Dict[str, Any]],
) -> tuple[str, Dict[str, Any], bool, bool]:
    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")
    slug_state = _normalize_slug_value(slug_state)
    slug_submitted = False
    form_error = False

    state_dict: Dict[str, Any] = vision_state if isinstance(vision_state, dict) else {}

    if verify_clicked:
        candidate = _normalize_slug_value(slug_input)
        valid, message = _validate_candidate_slug(candidate)
        if not valid:
            if message:
                st.error(message)
            _state_set("slug", "")
            return "", state_dict, slug_submitted, True
        slug_state = candidate
        _state_set("slug", slug_state)
        slug_submitted = True

    slug = _normalize_slug_value(slug_state)

    if not slug and state_dict:
        persisted_slug = _normalize_slug_value(str(state_dict.get("slug") or ""))
        if persisted_slug:
            slug = persisted_slug
            _state_set("slug", persisted_slug)

    if not slug:
        return "", state_dict, slug_submitted, form_error

    if not state_dict or state_dict.get("slug") != slug:
        state_dict = {
            "slug": slug,
            "client_name": "",
            "verified": False,
            "needs_creation": False,
            "pdf_bytes": None,
            "pdf_filename": None,
            "workspace_created": False,
            "base_dir": None,
            "yaml_paths": {},
            "mapping_yaml": "",
            "cartelle_yaml": "",
        }
    _state_set("vision_workflow", state_dict)
    return slug, state_dict, slug_submitted, form_error


def render_workspace_summary(
    slug: str,
    vision_state: Dict[str, Any],
    slug_submitted: bool,
    log: Optional[logging.Logger],
) -> tuple[bool, str, str]:
    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")
    workspace_dir = _workspace_dir_for(slug)
    workspace_exists = workspace_dir.exists()

    if slug_submitted:
        if workspace_exists and not vision_state.get("workspace_created"):
            return _enter_existing_workspace(slug, vision_state.get("client_name", ""))
        vision_state["verified"] = True
        vision_state["needs_creation"] = True
        _state_set("vision_workflow", vision_state)
        st.success("Cliente nuovo: carica il Vision Statement e crea il workspace.")

    if not vision_state.get("verified", False):
        return False, slug, vision_state.get("client_name", "")

    client_name = st.text_input(
        "Nome cliente",
        value=vision_state.get("client_name", ""),
        key="ls_name",
    ).strip()
    vision_state["client_name"] = client_name

    uploaded_pdf = st.file_uploader(
        "Vision Statement (PDF)",
        type=["pdf"],
        accept_multiple_files=False,
        key="ls_pdf",
        help="Carica il Vision Statement. VerrÃ  salvato come config/VisionStatement.pdf quando crei il workspace.",
    )
    if uploaded_pdf is not None:
        raw_pdf = uploaded_pdf.read()
        if raw_pdf:
            vision_state["pdf_bytes"] = raw_pdf
            vision_state["pdf_filename"] = uploaded_pdf.name
            st.success(f"PDF caricato: {uploaded_pdf.name}")
        else:
            st.warning("File PDF vuoto: riprova il caricamento.")
        _state_set("vision_workflow", vision_state)

    create_disabled = not client_name or vision_state.get("pdf_bytes") is None
    if st.button(
        "Crea workspace + carica PDF",
        key="ls_create_workspace",
        type="primary",
        width="stretch",
        disabled=create_disabled,
    ):
        pdf_bytes = cast(Optional[bytes], vision_state.get("pdf_bytes"))
        if not pdf_bytes:
            _st_notify("error", "Carica il Vision Statement prima di procedere.")
        else:
            try:
                ensure_local_workspace_for_ui(slug, client_name or slug, vision_statement_pdf=pdf_bytes)
                ctx = get_client_context(slug, interactive=False, require_env=False)
                if ctx.base_dir is None:
                    raise ConfigError("Workspace creato ma base_dir non disponibile.")
                base_dir = Path(ctx.base_dir)
                vision_state["base_dir"] = str(base_dir)
                pdf_path = ensure_within_and_resolve(base_dir, base_dir / "config" / "VisionStatement.pdf")
                result = vision_services.provision_from_vision(
                    ctx,
                    log or get_structured_logger("ui.vision_provision"),
                    slug=slug,
                    pdf_path=pdf_path,
                )
                yaml_paths = cast(Dict[str, str], result.get("yaml_paths") or {})
                vision_state["yaml_paths"] = yaml_paths
                vision_state["workspace_created"] = True
                vision_state["needs_creation"] = False
                _state_set("slug", slug)
                _state_set("client_name", client_name or slug)
                st.success("Workspace creato e YAML generati.")
                try:
                    base_dir = Path(vision_state["base_dir"])
                    mapping_abs = str(ensure_within_and_resolve(base_dir, Path(yaml_paths.get("mapping", ""))))
                    cartelle_abs = str(ensure_within_and_resolve(base_dir, Path(yaml_paths.get("cartelle_raw", ""))))
                    st.json({"mapping": mapping_abs, "cartelle_raw": cartelle_abs}, expanded=False)
                except Exception:
                    pass
            except ConfigError as exc:
                if log:
                    log.warning("landing.workspace_creation_failed", extra={"slug": slug, "error": str(exc)})
                _st_notify("error", str(exc))
            except Exception:  # pragma: no cover
                if log:
                    log.exception("landing.workspace_creation_failed", extra={"slug": slug})
                _st_notify("error", "Errore durante la creazione del workspace. Controlla i log.")
            finally:
                _state_set("vision_workflow", vision_state)

    if not vision_state.get("workspace_created"):
        return False, slug, client_name

    base_dir_str = cast(Optional[str], vision_state.get("base_dir"))
    yaml_paths = cast(Dict[str, str], vision_state.get("yaml_paths") or {})
    if not base_dir_str or "mapping" not in yaml_paths or "cartelle_raw" not in yaml_paths:
        st.warning("Workspace creato ma non sono disponibili gli YAML generati.")
        return False, slug, client_name

    base_dir_path = Path(base_dir_str)
    try:
        mapping_path = ensure_within_and_resolve(base_dir_path, Path(yaml_paths["mapping"]))
        cartelle_path = ensure_within_and_resolve(base_dir_path, Path(yaml_paths["cartelle_raw"]))
        mapping_content = read_text_safe(base_dir_path, mapping_path, encoding="utf-8")
        cartelle_content = read_text_safe(base_dir_path, cartelle_path, encoding="utf-8")
    except Exception:
        st.warning("Non Ã¨ stato possibile leggere le ultime configurazioni YAML generate.")
        return False, slug, client_name

    with st.expander("YAML generati (vision/cartelle)", expanded=False):
        st.code(mapping_content, language="yaml")
        st.code(cartelle_content, language="yaml")

    return True, slug, client_name


def render_landing_slug(log: Optional[logging.Logger] = None) -> Tuple[bool, str, str]:
    """Landing slug-first con verifica e bootstrap Vision Statement."""

    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")

    slug_state = cast(str, _state_get("slug", "") or "")
    vision_state = cast(Optional[Dict[str, Any]], _state_get("vision_workflow"))

    slug_input, verify_clicked = render_header_form(slug_state, log)
    slug, state_dict, slug_submitted, form_error = handle_verify_workflow(
        slug_state=slug_state,
        slug_input=slug_input,
        verify_clicked=verify_clicked,
        vision_state=vision_state,
    )

    if not slug or form_error:
        return False, "", ""

    return render_workspace_summary(
        slug=slug,
        vision_state=state_dict,
        slug_submitted=slug_submitted,
        log=log,
    )
