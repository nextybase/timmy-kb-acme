# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/landing_slug.py
from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from types import TracebackType
from typing import Any, ContextManager, Dict, Literal, Optional, Tuple, cast

import yaml

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, InvalidSlug
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe, validate_slug
from pre_onboarding import ensure_local_workspace_for_ui
from semantic.validation import validate_context_slug
from ui.services import vision_provision as vision_services
from ui.utils.branding import render_brand_header

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
            # In alcune versioni Streamlit può sollevare eccezioni interne di rerun: ignoriamo.
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
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "output" / f"timmy-kb-{slug}"


def _request_shutdown(logger: Optional[logging.Logger]) -> None:
    try:
        (logger or logging.getLogger("ui.landing_slug")).info("ui.shutdown_request")
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


def _base_dir_for(slug: str) -> Path:
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
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
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
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


# Legacy helper mantenuto per compatibilità con i test esistenti
def _render_logo() -> None:
    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        include_anchor=True,
        subtitle="Verifica slug cliente per avviare l'onboarding.",
        show_logo=False,
    )


def render_landing_slug(log: Optional[logging.Logger] = None) -> Tuple[bool, str, str]:
    """Landing slug-first con verifica e bootstrap Vision Statement."""

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

    c1, c2, c3 = st.columns([1, 2, 1])
    slug_state = _state_get("slug", "")
    verify_clicked = False
    form_error = False
    slug_submitted = False
    with c2:
        with _safe_form("ls_slug_form", clear_on_submit=False):
            slug_input = st.text_input(
                "Slug cliente",
                value=slug_state,
                key="ls_slug",
                placeholder="es. acme",
            )
            verify_clicked = _safe_form_submit(
                "Verifica cliente",
                type="primary",
            )
        if bool(os.getenv("UI_ALLOW_EXIT", "").strip()):
            st.button("Esci", key="ls_exit", on_click=lambda: _request_shutdown(log), width="stretch")

    if verify_clicked:
        candidate = (slug_input or "").strip()
        if not candidate:
            st.error("Inserisci uno slug.")
            _state_set("slug", "")
            slug_state = ""
            form_error = True
        else:
            try:
                validate_slug(candidate)
            except InvalidSlug:
                st.error("Slug non valido. Usa solo minuscole, numeri e trattini.")
                form_error = True
            else:
                slug_state = candidate
                slug_submitted = True
                _state_set("slug", slug_state)

    slug = (slug_state or "").strip()
    vision_state = cast(Optional[Dict[str, Any]], _state_get("vision_workflow"))

    if not slug and isinstance(vision_state, dict):
        persisted_slug = str(vision_state.get("slug") or "").strip()
        if persisted_slug:
            slug = persisted_slug
            slug_state = persisted_slug
            _state_set("slug", persisted_slug)

    if not slug or form_error:
        return False, "", ""

    if not vision_state or vision_state.get("slug") != slug:
        vision_state = {
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
        _state_set("vision_workflow", vision_state)

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
        help="Carica il Vision Statement. VerrÃ  salvato come config/VisionStatement.pdf quando crei il workspace.",
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
                ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
                if ctx.base_dir is None:
                    raise ConfigError("Workspace creato ma base_dir non disponibile.")
                base_dir = Path(ctx.base_dir)
                vision_state["base_dir"] = str(base_dir)
                pdf_path = ensure_within_and_resolve(base_dir, base_dir / "config" / "VisionStatement.pdf")
                result = vision_services.provision_from_vision(
                    ctx,
                    log or logging.getLogger("ui.vision_provision"),
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
    except Exception:  # pragma: no cover
        mapping_content = vision_state.get("mapping_yaml", "")
        cartelle_content = vision_state.get("cartelle_yaml", "")
    else:
        vision_state["mapping_yaml"] = mapping_content
        vision_state["cartelle_yaml"] = cartelle_content
        _state_set("vision_workflow", vision_state)

    st.markdown("### YAML generati (modificabili)")

    with st.form("yaml_editor_form"):
        updated_vision = st.text_area(
            "semantic/semantic_mapping.yaml",
            value=vision_state.get("mapping_yaml", ""),
            height=280,
            key="ls_mapping_text",
        )
        updated_cartelle = st.text_area(
            "semantic/cartelle_raw.yaml",
            value=vision_state.get("cartelle_yaml", ""),
            height=280,
            key="ls_cartelle_text",
        )
        if _safe_form_submit("Valida & Salva"):
            try:
                # --- Parse YAML (mapping + cartelle) ---
                try:
                    map_obj = yaml.safe_load(updated_vision) or {}
                    cart_obj = yaml.safe_load(updated_cartelle) or {}
                except Exception as e:
                    raise ConfigError(f"YAML non valido: {e}") from e

                # --- Validazione MAPPING: hard-fail prima di scrivere ---
                validate_context_slug(map_obj, expected_slug=slug)

                # --- CARTELLE: auto-heal se context/slug assente, hard-fail se mismatch ---
                changed_cartelle = False
                if not isinstance(cart_obj, dict):
                    cart_obj = {}
                    changed_cartelle = True
                ctx_obj = cart_obj.get("context")
                if not isinstance(ctx_obj, dict):
                    cart_obj["context"] = {"slug": slug}
                    changed_cartelle = True
                else:
                    raw = ctx_obj.get("slug")
                    payload_slug = raw.strip() if isinstance(raw, str) else ""
                    if not payload_slug:
                        ctx_obj["slug"] = slug
                        changed_cartelle = True

                # Validazione finale su cartelle (SSoT)
                validate_context_slug(cart_obj, expected_slug=slug)

                # Se auto-heal applicato, aggiorna il testo da salvare
                if changed_cartelle:
                    updated_cartelle = yaml.safe_dump(cart_obj, allow_unicode=True, sort_keys=False, width=100)

                # --- Scritture atomiche con path-safety (solo dopo validazione) ---
                target_map = ensure_within_and_resolve(base_dir_path, Path(yaml_paths["mapping"]))
                target_cart = ensure_within_and_resolve(base_dir_path, Path(yaml_paths["cartelle_raw"]))
                safe_write_text(target_map, updated_vision)
                safe_write_text(target_cart, updated_cartelle)
                vision_state["mapping_yaml"] = updated_vision
                vision_state["cartelle_yaml"] = updated_cartelle
                st.success("YAML aggiornati.")
            except ConfigError as exc:  # pragma: no cover
                if log:
                    log.exception("landing.save_yaml_failed", extra={"slug": slug})
                if st is not None:
                    st.error(str(exc))
                raise
            except Exception:  # pragma: no cover
                if log:
                    log.exception("landing.save_yaml_failed", extra={"slug": slug})
                _st_notify(
                    "error",
                    "Impossibile salvare gli YAML. Slug incoerente o YAML non valido.",
                )
            finally:
                _state_set("vision_workflow", vision_state)

    if st.button("Vai alla configurazione", key="ls_go_configuration", type="primary", width="stretch"):
        vision_state["workspace_committed"] = True
        _state_set("vision_workflow", vision_state)
        _state_set("client_locked", True)
        _state_set("active_section", "Configurazione")
        try:
            _safe_rerun()
        except Exception:  # pragma: no cover
            pass

    return False, slug, client_name
