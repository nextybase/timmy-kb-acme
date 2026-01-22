# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/landing_slug.py
from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, cast

from pipeline.env_utils import get_bool
from pipeline.exceptions import ConfigError, InvalidSlug
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe, validate_slug
from pipeline.workspace_layout import WorkspaceLayout
from timmy_kb.cli.pre_onboarding import ensure_local_workspace_for_ui
from ui.config_store import get_vision_model
from ui.utils.context_cache import get_client_context
from ui.utils.repo_root import get_repo_root
from ui.utils.workspace import get_ui_workspace_layout

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


def _require_streamlit() -> Any:
    if st is None:
        raise RuntimeError("Streamlit not available")
    return st


def _safe_rerun() -> None:
    """Richiede un rerun Streamlit se disponibile, senza dipendere da src.ui.app."""
    if st is None:
        return
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        try:
            rerun_fn()
        except Exception as exc:
            # In alcune versioni Streamlit può sollevare eccezioni interne di rerun: ignoriamo.
            log = get_structured_logger("ui.landing_slug")
            log.warning("ui.landing_slug.safe_rerun_failed", extra={"error": repr(exc)})


REPO_ROOT = get_repo_root(allow_env=True)

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


CLIENT_CONTEXT_ERROR_MSG = (
    "ClientContext non disponibile. Esegui pre_onboarding.ensure_local_workspace_for_ui o imposta REPO_ROOT_DIR."
)


def _reset_to_landing() -> None:
    """Reimposta lo stato UI e torna alla landing (slug vuoto)."""
    st_module = _require_streamlit()
    preserve = {"phase", _ui_key("phase")}
    for key in list(st_module.session_state.keys()):
        if key not in preserve:
            st_module.session_state.pop(key, None)
    _state_set("slug", "")
    _safe_rerun()


def _resolve_layout(slug: str) -> WorkspaceLayout | None:
    try:
        return get_ui_workspace_layout(slug, require_env=False)
    except (ConfigError, InvalidSlug):
        return None
    except Exception as exc:
        log = get_structured_logger("ui.landing_slug")
        log.exception(
            "ui.landing_slug.resolve_layout_failed",
            extra={"slug": slug, "error": repr(exc)},
        )
        raise


def _layout_missing_message(slug: str) -> str:
    return (
        f"Workspace '{slug}' non trovato o layout invalido. Usa pipeline.workspace_bootstrap "
        "(bootstrap_client_workspace/migrate_or_repair_workspace/ bootstrap_dummy_workspace) per creare o riparare "
        "il workspace prima di aprire la UI."
    )


def _workspace_dir_for(slug: str, *, layout: WorkspaceLayout | None = None) -> Path:
    if layout is None:
        raise ConfigError(
            "Workspace layout non disponibile: assicurati di avere un layout valido o usa le API "
            "di bootstrap in pipeline.workspace_bootstrap (bootstrap_client_workspace/migrate_or_repair_workspace).",
            slug=slug,
        )
    return cast(Path, layout.repo_root_dir)


def _request_shutdown(logger: Optional[logging.Logger]) -> None:
    log = logger or get_structured_logger("ui.landing_slug")
    try:
        log.info("ui.shutdown_request", extra={"pid": os.getpid()})
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception as exc:
        # Evita silent shutdown: lascia almeno traccia prima dell'exit forzato.
        log.warning("ui.shutdown_request_failed", extra={"error": repr(exc)})
        os._exit(0)


def _repo_root_dir_for(slug: str) -> Path:
    try:
        ctx = get_client_context(slug, require_env=False)
    except Exception as exc:
        raise RuntimeError(CLIENT_CONTEXT_ERROR_MSG) from exc

    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if isinstance(repo_root_dir, Path):
        return repo_root_dir

    raw_dir = getattr(ctx, "raw_dir", None)
    if isinstance(raw_dir, Path):
        return raw_dir.parent

    raise RuntimeError(CLIENT_CONTEXT_ERROR_MSG)


def _st_notify(level: str, message: str) -> None:
    """Invoca st.<level> se disponibile, altrimenti fallback a warning/info.

    Compatibile con stub/dummy usati nei test dove `st.error`/`st.warning`
    possono non esistere. Non solleva eccezioni.
    """
    log = get_structured_logger("ui.landing_slug")
    if st is None:
        log.warning("ui.landing_slug.notify_unavailable", extra={"requested_level": level})
        return
    # Prova il livello richiesto, poi degrada a warning/info
    for name in (level, "warning", "info"):
        fn = getattr(st, name, None)
        if callable(fn):
            try:
                fn(message)
                if name != level:
                    log.warning(
                        "ui.landing_slug.notify_degraded",
                        extra={"requested_level": level, "used_method": name},
                    )
                return
            except Exception as exc:
                log.warning(
                    "ui.landing_slug.notify_failed",
                    extra={"requested_level": level, "used_method": name, "error": repr(exc)},
                )
                continue
    log.warning("ui.landing_slug.notify_unhandled", extra={"requested_level": level})


def _enter_existing_workspace(slug: str, fallback_name: str) -> Tuple[bool, str, str]:
    _require_streamlit()
    client_name: str = fallback_name or slug
    try:
        ctx = get_client_context(slug, require_env=False)
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
    _safe_rerun()
    return True, slug, client_name


def _render_logo() -> None:
    """Render del logo nella landing (usato dai test UI)."""
    _require_streamlit()
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
    _require_streamlit()
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
        with st.form("ls_slug_form", clear_on_submit=False):
            slug_input = st.text_input("Slug cliente", value=slug_state, key="ls_slug", placeholder="es. acme")
            verify_clicked = st.form_submit_button("Verifica cliente", type="primary")
        if get_bool("UI_ALLOW_EXIT", default=False):
            st.button("Esci", key="ls_exit", on_click=lambda: _request_shutdown(log), width="stretch")
    return slug_input, verify_clicked


def handle_verify_workflow(
    slug_state: str,
    slug_input: str,
    verify_clicked: bool,
    vision_state: Optional[Dict[str, Any]],
) -> tuple[str, Dict[str, Any], bool, bool]:
    _require_streamlit()
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
            "repo_root_dir": None,
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
    _require_streamlit()
    layout = _resolve_layout(slug)
    if layout is None:
        _st_notify("error", _layout_missing_message(slug))
        return False, slug, vision_state.get("client_name", "")
    workspace_dir = _workspace_dir_for(slug, layout=layout)
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
        help="Carica il Vision Statement. Verrà salvato come config/VisionStatement.pdf quando crei il workspace.",
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
                ctx = get_client_context(slug, require_env=False)
                if ctx.repo_root_dir is None:
                    raise ConfigError("Workspace creato ma repo_root_dir non disponibile.")
                repo_root_dir = Path(ctx.repo_root_dir)
                vision_state["repo_root_dir"] = str(repo_root_dir)
                pdf_path = ensure_within_and_resolve(
                    repo_root_dir,
                    repo_root_dir / "config" / "VisionStatement.pdf",
                )
                result = vision_services.provision_from_vision_with_config(
                    ctx,
                    log or get_structured_logger("ui.vision_provision"),
                    slug=slug,
                    pdf_path=pdf_path,
                    model=get_vision_model(),
                )
                yaml_paths = {"mapping": cast(str, result.get("mapping", ""))}
                vision_state["yaml_paths"] = yaml_paths
                vision_state["workspace_created"] = True
                vision_state["needs_creation"] = False
                _state_set("slug", slug)
                _state_set("client_name", client_name or slug)
                st.success("Workspace creato e YAML generati.")
                try:
                    repo_root_dir = Path(vision_state["repo_root_dir"])
                    mapping_abs = str(ensure_within_and_resolve(repo_root_dir, Path(yaml_paths.get("mapping", ""))))
                    st.json({"mapping": mapping_abs}, expanded=False)
                except Exception as exc:
                    # Non bloccare la UX, ma evita silent degradation: traccia l'errore.
                    (log or get_structured_logger("ui.landing_slug")).warning(
                        "ui.landing_slug.paths_box_failed",
                        extra={"slug": slug, "error": repr(exc)},
                    )
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

    repo_root_dir_str = cast(Optional[str], vision_state.get("repo_root_dir"))
    yaml_paths = cast(Dict[str, str], vision_state.get("yaml_paths") or {})
    if not repo_root_dir_str or "mapping" not in yaml_paths:
        st.warning("Workspace creato ma non sono disponibili gli YAML generati.")
        return False, slug, client_name

    repo_root_dir_path = Path(repo_root_dir_str)
    try:
        mapping_path = ensure_within_and_resolve(repo_root_dir_path, Path(yaml_paths["mapping"]))
        mapping_content = read_text_safe(repo_root_dir_path, mapping_path, encoding="utf-8")
    except Exception:
        st.warning("Non è stato possibile leggere le ultime configurazioni YAML generate.")
        return False, slug, client_name

    with st.expander("YAML generati (vision)", expanded=False):
        st.code(mapping_content, language="yaml")

    return True, slug, client_name


def render_landing_slug(log: Optional[logging.Logger] = None) -> Tuple[bool, str, str]:
    """Landing slug-first con verifica e bootstrap Vision Statement."""
    _require_streamlit()

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
