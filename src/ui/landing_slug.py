# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/landing_slug.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, open_for_read_bytes_selfguard, read_text_safe
from pipeline.provision_from_yaml import provision_directories_from_cartelle_raw
from ui.services import vision_provision as vision_services

st: Any | None
try:  # preferisce runtime soft-fail per import opzionali
    import streamlit as _st

    st = _st
except Exception:  # pragma: no cover
    st = None

CLIENT_CONTEXT_ERROR_MSG = (
    "ClientContext non disponibile. Esegui " "pre_onboarding.ensure_local_workspace_for_ui o imposta REPO_ROOT_DIR."
)

_PROGRESS_STEPS = [
    ("pdf", "PDF ricevuto"),
    ("snapshot", "Snapshot"),
    ("vision_yaml", "YAML vision"),
    ("cartelle_yaml", "YAML cartelle"),
]


_MODEL_OPTIONS = ["gpt-4.1-mini", "gpt-4.1", "gpt-4.1-nano"]


def _empty_progress_state() -> Dict[str, bool]:
    return {key: False for key, _ in _PROGRESS_STEPS}


def _base_dir_for(slug: str) -> Path:
    """Calcola la base directory per lo slug usando esclusivamente ClientContext.

    ClientContext è lo SSoT per i path: in caso di indisponibilità si segnala l'errore.
    """
    try:
        from pipeline.context import ClientContext
    except Exception as exc:
        raise RuntimeError(CLIENT_CONTEXT_ERROR_MSG) from exc

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


def render_landing_slug(log: Optional[logging.Logger] = None) -> Tuple[bool, str, str]:
    """Landing minimale: inizialmente solo slug; su slug nuovo mostra Nome+PDF+help.

    Restituisce: (locked, slug, client_name)
    """
    if st is None:
        raise RuntimeError("Streamlit non disponibile per la landing UI.")
    st.markdown("<div style='height: 6vh'></div>", unsafe_allow_html=True)

    # Banner in alto a destra
    try:
        ROOT = Path(__file__).resolve().parents[2]
        _logo = ROOT / "assets" / "next-logo.png"
        if _logo.exists():
            import base64 as _b64

            logo_path = ensure_within_and_resolve(ROOT, _logo)
            with open_for_read_bytes_selfguard(logo_path) as logo_file:
                _data = logo_file.read()
            _enc = _b64.b64encode(_data).decode("ascii")
            img_html = (
                "<img src='data:image/png;base64,"
                f"{_enc}"
                "' alt='NeXT' "
                "style='width:100%;height:auto;display:block;' />"
            )
            left, right = st.columns([4, 1])
            with right:
                st.markdown(img_html, unsafe_allow_html=True)
    except Exception:
        pass

    # Input slug centrato
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        slug: str = (
            st.text_input(
                "Slug cliente",
                value=st.session_state.get("slug", ""),
                key="ls_slug",
                placeholder="es. acme",
            )
            or ""
        )

    slug = (slug or "").strip()
    if not slug:
        return False, "", ""

    base_dir: Optional[Path] = None
    base_dir_error: Optional[str] = None
    try:
        base_dir = _base_dir_for(slug)
    except RuntimeError as err:
        base_dir_error = str(err)

    # Caso A: workspace esistente → carica nome da config se presente
    if base_dir is not None and base_dir.exists():
        client_name: str = slug
        try:
            from pipeline.config_utils import get_client_config
            from pipeline.context import ClientContext

            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            cfg = get_client_config(ctx) or {}
            client_name = str(cfg.get("client_name") or slug)
        except Exception:
            client_name = slug

        st.session_state["slug"] = slug
        st.session_state["client_name"] = client_name
        st.session_state["client_locked"] = True
        st.session_state["active_section"] = "Configurazione"
        try:
            st.rerun()
        except Exception:
            pass
        return True, slug, client_name

    if base_dir_error:
        st.caption(base_dir_error)

    # Caso B: workspace nuovo → workflow Vision onboarding
    st.caption("Nuovo cliente rilevato.")
    vision_state = st.session_state.setdefault(
        "vision_workflow",
        {
            "slug": slug,
            "base_dir": None,
            "uploaded_pdf_path": None,
            "yaml_paths": None,
            "vision_result": None,
            "provision_result": None,
            "progress": _empty_progress_state(),
            "last_model": "gpt-4.1-mini",
            "force_pending": False,
        },
    )
    if vision_state["slug"] != slug:
        vision_state.update(
            {
                "slug": slug,
                "base_dir": None,
                "uploaded_pdf_path": None,
                "yaml_paths": None,
                "vision_result": None,
                "provision_result": None,
                "progress": _empty_progress_state(),
                "last_model": "gpt-4.1-mini",
                "force_pending": False,
            }
        )

    client_name = (
        st.text_input(
            "Nome cliente",
            value=st.session_state.get("client_name", ""),
            key="ls_name",
        )
        or ""
    )
    pdf = st.file_uploader(
        "Vision Statement (PDF)",
        type=["pdf"],
        accept_multiple_files=False,
        key="ls_pdf",
        help=(
            "Carica il Vision Statement (PDF). Verrà archiviato nel workspace del cliente "
            "e potrà essere aggiornato in seguito."
        ),
    )
    st.info(
        "Carica il Vision Statement (PDF). Verrà archiviato nel workspace del cliente "
        "e potrà essere aggiornato in seguito.",
        icon="ℹ️",
    )

    def _prepare_context(pdf_bytes: Optional[bytes]) -> Tuple[Optional["ClientContext"], Optional[Path]]:
        try:
            from pipeline.context import ClientContext
        except Exception:
            if log:
                log.exception("landing.ctx_import_failed", extra={"slug": slug})
            st.error("ClientContext non disponibile. Controlla i log.")
            return None, None

        try:
            if pdf_bytes is not None:
                from pre_onboarding import ensure_local_workspace_for_ui

                ensure_local_workspace_for_ui(
                    slug,
                    client_name=client_name or slug,
                    vision_statement_pdf=pdf_bytes,
                )
        except Exception:  # pragma: no cover
            if log:
                log.exception("landing.ensure_workspace_failed", extra={"slug": slug})
            st.error("Errore nella creazione del workspace o nel salvataggio del PDF. Controlla i log.")
            return None, None

        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
        except Exception:  # pragma: no cover
            if log:
                log.exception("landing.ctx_load_failed", extra={"slug": slug})
            st.error(f"Errore nel caricamento del contesto per slug '{slug}'.")
            return None, None

        base_dir = Path(ctx.base_dir)
        try:
            pdf_path = ensure_within_and_resolve(base_dir, base_dir / "config" / "VisionStatement.pdf")
        except Exception:  # pragma: no cover
            if log:
                log.exception("landing.pdf_missing", extra={"slug": slug})
            st.error("VisionStatement.pdf non trovato nel workspace. Carica nuovamente il file e riprova.")
            return None, None

        st.session_state["slug"] = slug
        st.session_state["client_name"] = client_name
        vision_state["base_dir"] = str(base_dir)
        vision_state["uploaded_pdf_path"] = str(pdf_path)
        return ctx, pdf_path

    def _render_progress() -> None:
        if not any(vision_state["progress"].values()):
            return
        steps = " → ".join(
            f"{'✅' if vision_state['progress'].get(key) else '⏳'} {label}" for key, label in _PROGRESS_STEPS
        )
        st.markdown(f"**Avanzamento pipeline:** {steps}")

    def _safe_read_yaml(path_value: Optional[str]) -> Optional[str]:
        base_dir_str = vision_state.get("base_dir")
        if not base_dir_str or not path_value:
            return None
        try:
            base_dir_path = Path(base_dir_str)
            return cast(str, read_text_safe(base_dir_path, Path(path_value), encoding="utf-8"))
        except Exception:  # pragma: no cover
            return None

    def _render_yaml_preview() -> None:
        yaml_paths = vision_state.get("yaml_paths") or {}
        if not yaml_paths:
            return
        st.markdown("---")
        result_meta = vision_state.get("vision_result") or {}
        meta_line = f"Modello `{vision_state.get('last_model', 'gpt-4.1-mini')}`"
        if result_meta.get("generated_at"):
            meta_line += f" – {result_meta['generated_at']}"
        st.caption(meta_line)
        with st.expander("Anteprima semantic/vision_statement.yaml", expanded=False):
            vision_yaml = _safe_read_yaml(yaml_paths.get("vision"))
            if vision_yaml is not None:
                st.code(vision_yaml, language="yaml")
            else:
                st.warning("Impossibile leggere semantic/vision_statement.yaml.")
        with st.expander("Anteprima semantic/cartelle_raw.yaml", expanded=False):
            cartelle_yaml = _safe_read_yaml(yaml_paths.get("cartelle_raw"))
            if cartelle_yaml is not None:
                st.code(cartelle_yaml, language="yaml")
            else:
                st.warning("Impossibile leggere semantic/cartelle_raw.yaml.")

    def _run_generation(*, model: str, pdf_bytes: Optional[bytes], force: bool = False) -> None:
        if pdf_bytes is None and not vision_state.get("uploaded_pdf_path"):
            st.error("Carica prima il VisionStatement.pdf.")
            return

        ctx, pdf_path = _prepare_context(pdf_bytes)
        if ctx is None or pdf_path is None:
            return

        progress_bar = st.progress(0, text="Vision AI: PDF ricevuto")
        vision_state["progress"] = _empty_progress_state()
        vision_state["yaml_paths"] = None
        vision_state["vision_result"] = None
        vision_state["provision_result"] = None
        vision_state["force_pending"] = False
        vision_state["progress"]["pdf"] = True
        progress_bar.progress(25, text="PDF ricevuto")

        try:
            result = vision_services.provision_from_vision(
                ctx,
                log or logging.getLogger("ui.vision_provision"),
                slug=slug,
                pdf_path=pdf_path,
                model=model,
                force=force,
            )
        except ConfigError as exc:
            progress_bar.empty()
            if log:
                log.warning("landing.vision_config_error", extra={"slug": slug, "error": str(exc)})
            st.error(str(exc))
            st.caption("Consulta `logs/vision_provision.log` nel workspace per maggiori dettagli.")
            vision_state["progress"] = _empty_progress_state()
            return
        except Exception:  # pragma: no cover
            progress_bar.empty()
            if log:
                log.exception("landing.vision_generation_failed", extra={"slug": slug})
            st.error("Errore nella generazione AI. Controlla i log per i dettagli.")
            vision_state["progress"] = _empty_progress_state()
            return

        if not result.get("regenerated", True):
            progress_bar.empty()
            vision_state["progress"] = _empty_progress_state()
            vision_state["yaml_paths"] = result.get("yaml_paths") or {}
            vision_state["vision_result"] = result
            vision_state["last_model"] = model
            vision_state["force_pending"] = True
            st.warning("Artefatti già presenti (hash invariato). Vuoi rigenerare?")
            return

        vision_state["vision_result"] = result
        vision_state["yaml_paths"] = result.get("yaml_paths") or {}
        vision_state["last_model"] = model
        vision_state["force_pending"] = False
        vision_state["progress"]["snapshot"] = True
        progress_bar.progress(50, text="Snapshot")
        vision_state["progress"]["vision_yaml"] = True
        progress_bar.progress(75, text="YAML vision")
        vision_state["progress"]["cartelle_yaml"] = True
        progress_bar.progress(100, text="YAML cartelle")
        progress_bar.empty()
        st.success("Pipeline Vision completata.")

    def _run_provisioning() -> None:
        yaml_paths = vision_state.get("yaml_paths") or {}
        cartelle_path_str = yaml_paths.get("cartelle_raw")
        if not cartelle_path_str:
            st.error("Nessun YAML cartelle disponibile. Genera il Vision prima di approvare.")
            return
        ctx, _ = _prepare_context(None)
        if ctx is None:
            return
        try:
            result = provision_directories_from_cartelle_raw(
                ctx,
                log or logging.getLogger("ui.vision_provision"),
                slug=slug,
                yaml_path=Path(cartelle_path_str),
            )
        except ConfigError as exc:
            st.error(str(exc))
            return
        except Exception:  # pragma: no cover
            if log:
                log.exception("landing.provision_failed", extra={"slug": slug})
            st.error("Errore durante la creazione delle cartelle. Controlla i log.")
            return

        vision_state["provision_result"] = result
        created = len(result.get("created", []))
        skipped = len(result.get("skipped", []))
        try:
            st.toast("Cartelle create", icon="✅")
        except Exception:  # pragma: no cover
            pass
        st.success(f"Provisioning completato. Create: {created}, skipped: {skipped}.")

    disabled_create = not (slug and client_name and pdf is not None)
    disabled_generate = not (slug and client_name and pdf is not None)
    col_create, col_generate = st.columns(2)
    with col_create:
        if st.button("Crea workspace cliente", key="ls_create_ws", disabled=disabled_create):
            ctx, pdf_path = _prepare_context(pdf.getvalue() if pdf is not None else None)
            if ctx and pdf_path:
                st.session_state["client_locked"] = True
                st.session_state["active_section"] = "Configurazione"
                st.success("Workspace creato con successo.")
                try:
                    st.rerun()
                except Exception:  # pragma: no cover
                    pass
    with col_generate:
        if st.button("Genera da Vision (AI)", key="ls_run_vision", type="primary", disabled=disabled_generate):
            _run_generation(
                model=vision_state.get("last_model", "gpt-4.1-mini"),
                pdf_bytes=pdf.getvalue() if pdf is not None else None,
            )

    _render_progress()
    _render_yaml_preview()

    if vision_state.get("force_pending"):
        st.warning("Artefatti già presenti (hash invariato). Vuoi rigenerare?")
        force_toggle = st.toggle("Rigenera forzatamente", key="vision_force_toggle")
        if force_toggle and st.button("Rigenera adesso", key="ls_force_regen", type="primary"):
            _run_generation(
                model=vision_state.get("last_model", "gpt-4.1-mini"),
                pdf_bytes=None,
                force=True,
            )
            vision_state["force_pending"] = False
            st.session_state.pop("vision_force_toggle", None)

    yaml_paths = vision_state.get("yaml_paths") or {}
    if yaml_paths:
        st.markdown("### Azioni successive")
        col_regen, col_prov = st.columns(2)
        with col_regen:
            last_model = vision_state.get("last_model", "gpt-4.1-mini")
            try:
                default_idx = _MODEL_OPTIONS.index(last_model)
            except ValueError:
                default_idx = 0
            selected_model = st.selectbox(
                "Modello",
                _MODEL_OPTIONS,
                index=default_idx,
                key="vision_model_select",
            )
            if st.button(f"Rigenera con modello {selected_model}", key="ls_regenerate"):
                _run_generation(model=selected_model, pdf_bytes=None, force=True)
        with col_prov:
            if st.button("Approva e crea cartelle", key="ls_approve", type="primary"):
                _run_provisioning()

    provision_result = vision_state.get("provision_result")
    if provision_result:
        created = provision_result.get("created", [])
        skipped = provision_result.get("skipped", [])
        st.success(f"Ultimo provisioning: create {len(created)}, skipped {len(skipped)}.")
        with st.expander("Dettaglio cartelle", expanded=False):
            if created:
                st.markdown("**Create**")
                for path_str in created:
                    st.write(f"- {path_str}")
            if skipped:
                st.markdown("**Skipped**")
                for path_str in skipped:
                    st.write(f"- {path_str}")
            if not created and not skipped:
                st.write("Nessuna cartella creata o saltata.")

    return False, slug, client_name
