# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/new_client.py
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, cast

from pipeline.beta_flags import is_beta_strict
from pipeline.capabilities.new_client import create_new_client_workspace
from pipeline.config_utils import get_client_config, get_drive_id
from pipeline.context import validate_slug
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.workspace_layout import WorkspaceLayout
from ui.chrome import header, sidebar
from ui.clients_store import ClientEntry, get_registry_paths, set_state, upsert_client
from ui.config_store import get_vision_model
from ui.constants import UI_PHASE_INIT, UI_PHASE_PROVISIONED, UI_PHASE_READY_TO_OPEN
from ui.errors import to_user_message
from ui.imports import getattr_if_callable, import_first
from ui.pages.registry import PagePaths
from ui.utils import clear_active_slug, set_slug
from ui.utils.config import resolve_ui_allow_local_only
from ui.utils.context_cache import get_client_context, invalidate_client_context
from ui.utils.control_plane import run_control_plane_tool
from ui.utils.repo_root import get_repo_root
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.status import status_guard
from ui.utils.stubs import get_streamlit
from ui.utils.workspace import get_ui_workspace_layout

st = get_streamlit()

if TYPE_CHECKING:
    from pipeline.context import ClientContext as ClientContextType
else:  # pragma: no cover
    ClientContextType = Any  # type: ignore[misc]

EnsureDriveCallable = Callable[..., Path]
_drive_runner = import_first(
    "ui.services.drive_runner",
    "src.ui.services.drive_runner",
)
_ensure_drive_minimal_impl = cast(
    Optional[EnsureDriveCallable],
    getattr_if_callable(_drive_runner, "ensure_drive_minimal_and_upload_config"),
)

_ensure_drive_minimal: Optional[EnsureDriveCallable]
if _ensure_drive_minimal_impl:
    _ensure_drive_minimal = _ensure_drive_minimal_impl
else:
    _ensure_drive_minimal = None


def ui_allow_local_only_enabled() -> bool:
    """Legge (o rilegge) il flag ui_allow_local_only dal settings runtime."""
    try:
        return resolve_ui_allow_local_only()
    except ConfigError as exc:
        st.error(f"{exc} Interrompo l'onboarding.")
        st.stop()
        raise


LOGGER = get_structured_logger("ui.new_client")

_LAYOUT_CACHE: dict[str, WorkspaceLayout] = {}


def _layout_for_slug(slug: str) -> WorkspaceLayout | None:
    key = (slug or "").strip().lower()
    if not key:
        return None
    cached = _LAYOUT_CACHE.get(key)
    if cached:
        return cached

    try:
        layout = get_ui_workspace_layout(key, require_drive_env=False)
    except Exception:
        return None
    _LAYOUT_CACHE[key] = layout
    return layout


def _require_layout(slug: str, layout: WorkspaceLayout | None = None) -> WorkspaceLayout:
    candidate = layout if layout is not None else _layout_for_slug(slug)
    if candidate is None:
        raise ConfigError(
            "Workspace layout non disponibile: usa pipeline.workspace_bootstrap per creare il workspace.",
            slug=slug,
        )
    return candidate


def _semantic_dir_client(slug: str, layout: WorkspaceLayout | None = None) -> Path:
    layout = _require_layout(slug, layout)
    return layout.semantic_dir


def _has_drive_ids(slug: str) -> bool:
    """Ritorna True se nel config del cliente sono presenti gli ID Drive minimi.

    Nota: dopo il provisioning Drive la UI può avere un contesto cache-ato.
    Per garantire determinismo (stato su disco = stato letto), forziamo reload.
    """
    try:
        invalidate_client_context(slug)
        ctx = get_client_context(slug, require_drive_env=False, force_reload=True)
    except Exception:
        return False
    try:
        cfg = get_client_config(ctx) or {}
    except Exception:
        return False
    return bool(get_drive_id(cfg, "raw_folder_id")) and bool(get_drive_id(cfg, "folder_id"))


def _exists_semantic_files(slug: str, layout: WorkspaceLayout | None = None) -> bool:
    sd = _semantic_dir_client(slug, layout=layout)
    return (sd / "semantic_mapping.yaml").exists()


def _open_error_modal(
    title: str,
    body: str,
    *,
    caption: str | None = None,
    on_force: Optional[Callable[[], bool]] = None,
    force_label: str = "Forza e prosegui",
) -> None:
    """
    Mostra un modal di errore con bottone 'Annulla'.
    - Richiede st.dialog (Streamlit >= 1.50).
    - Se `on_force` è fornito, mostra anche il bottone per forzare l'azione.
    """

    def _modal() -> None:
        st.error(body)
        if caption:
            st.caption(caption)
        col_force, col_cancel = st.columns(2)
        with col_force:
            if on_force is not None and st.button(force_label, type="primary"):
                try:
                    forced = on_force()
                    if forced:
                        st.rerun()
                except Exception as force_exc:
                    st.error(f"Impossibile forzare l'operazione: {force_exc}")
        with col_cancel:
            if st.button("Annulla", type="secondary"):
                return

    open_modal = st.dialog(title, width="large")
    modal_runner = open_modal(_modal)
    if callable(modal_runner):
        modal_runner()
    else:
        _modal()


def _log_diagnostics(
    slug: str,
    level: str,
    message: str,
    *,
    extra: Dict[str, Any],
    layout: WorkspaceLayout | None = None,
) -> None:
    """
    Scrive un evento nel log Diagnostica (WARNING-only by convention).
    Usiamo sempre livelli >= warning quando invochiamo questa funzione.
    """
    if layout is not None:
        _require_layout(slug, layout)
    logger = get_structured_logger("ui.diagnostics")
    log_method = getattr(logger, level, None)
    if callable(log_method):
        log_method(message, extra=extra)
    else:  # degradazione a warning se il livello non esiste
        logger.warning(message, extra=extra)


def _log_drive_capability_missing(
    slug: str,
    *,
    phase: str,
    strict: bool,
    helper_missing: bool,
    ids_missing: bool,
) -> None:
    payload = {
        "slug": slug,
        "phase": phase,
        "strict": bool(strict),
        "capability": "drive",
        "missing": {"helper": bool(helper_missing), "ids": bool(ids_missing)},
    }
    if strict:
        LOGGER.error("ui.drive.capability_missing", extra=payload)
    else:
        LOGGER.warning("ui.drive.capability_missing", extra=payload)


# Registry unificato (SSoT) via ui.clients_store
def _upsert_client_registry(slug: str, client_name: str, *, target_state: Optional[str] = "pronto") -> None:
    """
    Allinea il registro, impostando lo stato desiderato (default: 'pronto').
    Se `target_state` è None, preserva lo stato attuale (o 'nuovo' se assente).
    """
    from ui.clients_store import get_state  # import locale per evitare cicli

    current = (get_state(slug) or "").strip()
    desired = (target_state or current or "nuovo").strip() or "nuovo"
    entry = ClientEntry(slug=slug, nome=(client_name or "").strip() or slug, stato=desired)
    upsert_client(entry)
    if desired != current:
        set_state(slug, desired)


def _log_registry_failed(slug: str, exc: Exception, *, registry_path: Optional[Path] = None) -> None:
    payload = {
        "slug": slug,
        "type": exc.__class__.__name__,
        "error": str(exc),
    }
    if registry_path is not None:
        payload["path"] = str(registry_path)
    LOGGER.error("client_registry_failed", extra=payload)


def _register_client_after_vision(slug: str, client_name: str) -> None:
    try:
        _, registry_path = get_registry_paths()
    except Exception as exc:
        _log_registry_failed(slug, exc)
        st.error(f"Registry clienti non leggibile per slug={slug}. Causa: {exc}")
        st.stop()
        raise
    try:
        _upsert_client_registry(slug, client_name, target_state="nuovo")
    except Exception as exc:
        _log_registry_failed(slug, exc, registry_path=registry_path)
        st.error(
            f"Registry clienti non aggiornabile per slug={slug}. Path: {registry_path}. Causa: {exc}",
        )
        st.stop()
        raise
    LOGGER.info("client_registry_upserted", extra={"slug": slug, "path": str(registry_path)})  # cspell:ignore upserted


def _warn_drive_raw_skipped(
    slug: str,
    *,
    mapping_path: Path,
    raw_info: Optional[Dict[str, Any]],
    strict: bool,
) -> None:
    if not isinstance(raw_info, dict):
        return
    status = raw_info.get("drive_status")
    if status != "skipped":
        return
    reason = str(raw_info.get("drive_reason") or "unknown")
    payload = {"slug": slug, "reason": reason, "mapping": str(mapping_path)}
    if strict:
        LOGGER.error("drive_unavailable_raw_structure_skipped", extra=payload)
        raise ConfigError(
            "Drive non disponibile: struttura raw su Drive non creata.",
            slug=slug,
            file_path=str(mapping_path),
        )
    LOGGER.warning("drive_unavailable_raw_structure_skipped", extra=payload)
    st.warning(
        f"Drive non disponibile: struttura raw su Drive non creata. slug={slug} mapping={mapping_path} causa={reason}"
    )


# --------- UI ---------
header(None)
sidebar(None)

st.subheader("Nuovo cliente")

# La pagina "Nuovo cliente" non deve ereditare lo slug da alcun layer.
if not st.session_state.get("__new_client_slug_cleared", False):
    clear_active_slug(persist=True, update_query=True)
    st.session_state["__new_client_slug_cleared"] = True
    try:
        getattr(st, "rerun", lambda: None)()
    except Exception:
        pass

# Chiavi di stato UI (effimere, non persistite)
slug_state_key = "new_client.slug"
phase_state_key = "new_client.phase"

current_slug = st.session_state.get(slug_state_key, "")
current_phase = st.session_state.get(phase_state_key, UI_PHASE_INIT)

# Input
slug = st.text_input(
    "Slug cliente",
    placeholder="es. acme-srl",
    key="new_slug",
    value=current_slug or "",
    disabled=(current_phase in (UI_PHASE_READY_TO_OPEN, UI_PHASE_PROVISIONED)),
)
name = st.text_input(
    "Nome cliente (opzionale)",
    placeholder="es. ACME Srl",
    key="new_name",
    disabled=(current_phase in (UI_PHASE_READY_TO_OPEN, UI_PHASE_PROVISIONED)),
)
pdf = st.file_uploader(
    "Vision Statement (PDF)",
    type=["pdf"],
    key="new_vs_pdf",
    disabled=(current_phase in (UI_PHASE_READY_TO_OPEN, UI_PHASE_PROVISIONED)),
    help="Obbligatorio: sarà salvato come config/VisionStatement.pdf",
)

# Anteprima prompt Vision opzionale
preview_prompt = st.checkbox(
    "Mostra anteprima prompt Vision",
    value=False,
    key="vision_preview_prompt",
    help="Visualizza il testo generato e conferma con 'Prosegui' prima di inviare la richiesta.",
    disabled=(current_phase in (UI_PHASE_READY_TO_OPEN, UI_PHASE_PROVISIONED)),
)
if preview_prompt:
    st.info("Anteprima prompt Vision non disponibile nel flusso control-plane; usa Tools > Tuning per la preview.")

# Slug determinato localmente (non cambiamo fasi/stati finché non premi i pulsanti)
candidate_slug = (slug or "").strip()
effective_slug = (current_slug or candidate_slug) or ""
if candidate_slug:
    try:
        validate_slug(candidate_slug)
    except (ConfigError, ValueError) as exc:
        LOGGER.warning("ui.new_client.slug_sync_failed", extra={"slug": candidate_slug, "error": str(exc)})
    else:
        if st.session_state.get(slug_state_key) != candidate_slug:
            set_slug(candidate_slug, persist=False, update_query=False)
            st.session_state[slug_state_key] = candidate_slug

# ------------------------------------------------------------------
# STEP 1 - Inizializza Workspace (crea struttura + salva PDF + Vision → YAML)
# VISIBILE solo quando la fase UI è INIT
# ------------------------------------------------------------------
if current_phase == UI_PHASE_INIT:
    if st.button("Inizializza Workspace", type="primary", key="btn_init_ws", width="stretch"):
        s = candidate_slug
        progress = st.progress(0, text="Avvio inizializzazione...")

        # 1) Validazione slug (SSoT)
        try:
            validate_slug(s)
        except ConfigError as e:
            st.error(f"Slug non valido: {e}")
            st.caption("Formato atteso: minuscole, numeri e '-' (configurabile in config.yaml).")
            LOGGER.warning("ui.new_client.invalid_slug", extra={"slug": s, "error": str(e)})
            st.stop()

        # 2) PDF obbligatorio e non vuoto
        if pdf is None:
            st.error("Carica il Vision Statement (PDF) prima di procedere.")
            st.stop()
        pdf_bytes: Optional[bytes] = pdf.getvalue() if pdf is not None else None
        if not pdf_bytes:
            st.error("Il file PDF caricato è vuoto o non leggibile.")
            st.stop()

        client_name_value = (st.session_state.get("new_name") or name or "").strip()
        local_only_mode = ui_allow_local_only_enabled()
        enable_drive = not local_only_mode

        repo_root_dir = Path(get_repo_root(allow_env=False))

        def _progress_callback(pct: int, message: str) -> None:
            try:
                progress.progress(pct, text=message)
            except Exception:
                pass

        result: dict[str, Any]
        try:
            with status_guard(
                "Preparo il workspace locale...",
                expanded=True,
                error_label="Errore durante la preparazione del workspace",
            ) as status:
                result = create_new_client_workspace(
                    slug=s,
                    client_name=client_name_value,
                    pdf_bytes=pdf_bytes,
                    repo_root=repo_root_dir,
                    vision_model=get_vision_model(),
                    enable_drive=enable_drive,
                    ui_allow_local_only=local_only_mode,
                    ensure_drive_minimal=_ensure_drive_minimal,
                    run_control_plane_tool=run_control_plane_tool,
                    progress=_progress_callback,
                )
                if status is not None and hasattr(status, "update"):
                    status.update(label="Workspace locale pronto.", state="complete")
        except Exception as exc:
            title, body, caption = to_user_message(exc)
            _log_diagnostics(
                s,
                "warning",
                "ui.vision.error",
                extra={"slug": s, "type": exc.__class__.__name__, "err": str(exc).splitlines()[:1]},
                layout=None,
            )
            _open_error_modal(title, body, caption=caption)
            st.stop()

        layout = WorkspaceLayout.from_workspace(Path(result["workspace_root_dir"]), slug=s)
        cache_key = (s or "").strip().lower()
        if cache_key:
            _LAYOUT_CACHE[cache_key] = layout

        if isinstance(pdf_bytes, (bytes, bytearray)) and len(pdf_bytes) > 20 * 1024 * 1024:
            try:
                _log_diagnostics(
                    s,
                    "warning",
                    "ui.new_client.large_pdf",
                    extra={"slug": s, "bytes": len(pdf_bytes)},
                    layout=layout,
                )
            except Exception:
                pass

        drive_info = result["drive"]
        if drive_info.get("skipped_reason") == "local_only":
            LOGGER.info(
                "ui.drive.provisioning_skipped",
                extra={"slug": s, "reason": "allow_local_only", "local_only": True},
            )
            _log_diagnostics(
                s,
                "warning",
                "ui.drive.not_configured_local_only",
                extra={"slug": s, "phase": "init"},
                layout=layout,
            )
            try:
                progress.progress(60, text="Drive in modalità locale (skip provisioning).")
            except Exception:
                pass

        mapping_path = Path(result["semantic_mapping_path"])
        _warn_drive_raw_skipped(
            s,
            mapping_path=mapping_path,
            raw_info=result["vision"].get("raw_structure"),
            strict=is_beta_strict(),
        )

        if _exists_semantic_files(s, layout=layout):
            display_name = (client_name_value or "").strip() or s
            _register_client_after_vision(s, display_name)
            set_slug(s)
            st.session_state[slug_state_key] = s
            st.session_state[phase_state_key] = UI_PHASE_READY_TO_OPEN
            st.session_state["client_name"] = display_name
            st.success("Workspace inizializzato e YAML generati.")
            progress.progress(100, text="Vision completata.")
        else:
            st.error("Vision terminata ma i file attesi non sono presenti in semantic/.")

# ------------------------------------------------------------------
# STEP 2 - Apri workspace (solo Drive + finalizzazione stato)
# VISIBILE solo quando la fase UI è READY_TO_OPEN
# ------------------------------------------------------------------
if st.session_state.get(phase_state_key) == UI_PHASE_READY_TO_OPEN and (
    st.session_state.get(slug_state_key) or effective_slug
):
    eff = st.session_state.get(slug_state_key) or effective_slug
    layout = _require_layout(eff)
    if not _exists_semantic_files(eff, layout=layout):
        st.error("Per aprire il workspace serve semantic/semantic_mapping.yaml. Esegui prima 'Inizializza Workspace'.")
        st.stop()

    # Il controllo resta invariato, ma grazie al reload forzato
    # ora leggerà la configurazione aggiornata.
    has_drive_ids = _has_drive_ids(eff)
    local_only_mode = ui_allow_local_only_enabled()
    if not has_drive_ids:
        _log_drive_capability_missing(
            eff,
            phase="open",
            strict=False,
            helper_missing=_ensure_drive_minimal is None,
            ids_missing=True,
        )
        if not local_only_mode:
            st.error("Config privo degli ID Drive. Ripeti 'Inizializza Workspace' dopo aver configurato Drive.")
            st.stop()

    display_name = st.session_state.get("client_name") or (name or eff)

    if local_only_mode and not has_drive_ids:
        LOGGER.info("ui.wizard.local_fallback", extra={"slug": eff, "local_only": True})
        LOGGER.info("ui.wizard.local_only_requested", extra={"slug": eff, "local_only": True})
        _log_diagnostics(
            eff,
            "warning",
            "ui.drive.not_configured_local_only",
            extra={"slug": eff},
            layout=layout,
        )
        st.warning("Drive non configurato: modalita local-only attiva.")

    _upsert_client_registry(eff, display_name)
    st.session_state[phase_state_key] = UI_PHASE_PROVISIONED
    st.session_state["client_name"] = display_name

# ------------------------------------------------------------------
# STEP 3 - Link finale
# VISIBILE solo quando la fase UI è PROVISIONED
# ------------------------------------------------------------------
if st.session_state.get(phase_state_key) == UI_PHASE_PROVISIONED and (
    st.session_state.get(slug_state_key) or effective_slug
):
    eff = st.session_state.get(slug_state_key) or effective_slug
    # Navigazione basata su PagePaths: Beta 1.0 assume Streamlit modern.
    st.page_link(PagePaths.MANAGE, label="Vai a Gestisci cliente")
