# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/new_client.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, cast

from ui.pages.registry import PagePaths
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()
import yaml

from pipeline.beta_flags import is_beta_strict
from pipeline.config_utils import get_client_config, update_config_with_drive_ids
from pipeline.context import validate_slug
from pipeline.exceptions import ConfigError, WorkspaceLayoutInconsistent, WorkspaceLayoutInvalid, WorkspaceNotFound
from pipeline.file_utils import safe_write_bytes, safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.ownership import ensure_ownership_file
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.settings import Settings
from pipeline.system_self_check import run_system_self_check
from pipeline.workspace_bootstrap import bootstrap_client_workspace
from pipeline.workspace_layout import WorkspaceLayout
from pipeline.yaml_utils import yaml_read
from semantic.core import compile_document_to_vision_yaml
from ui.chrome import header, sidebar
from ui.clients_store import ClientEntry, set_state, upsert_client
from ui.constants import UI_PHASE_INIT, UI_PHASE_PROVISIONED, UI_PHASE_READY_TO_OPEN
from ui.errors import to_user_message
from ui.imports import getattr_if_callable, import_first
from ui.utils import clear_active_slug, set_slug
from ui.utils.context_cache import get_client_context, invalidate_client_context
from ui.utils.html import esc_url_component
from ui.utils.merge import deep_merge_dict
from ui.utils.repo_root import get_repo_root
from ui.utils.status import status_guard
from ui.utils.workspace import get_ui_workspace_layout

if TYPE_CHECKING:
    from pipeline.context import ClientContext
else:  # pragma: no cover
    ClientContext = Any  # type: ignore[misc]

_vision_module = import_first(
    "ui.services.vision_provision",
    "src.ui.services.vision_provision",
)
run_vision = getattr(_vision_module, "run_vision")

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


def _load_repo_settings() -> Settings:
    try:
        return Settings.load(get_repo_root())
    except Exception as exc:
        LOGGER.error(
            "ui.new_client.settings_load_failed",
            extra={"error": str(exc)},
        )
        raise ConfigError(
            "Impossibile caricare la configurazione: modalita runtime non determinabile.",
        ) from exc


def _resolve_ui_allow_local_only() -> bool:
    settings_obj = _load_repo_settings()
    try:
        return bool(settings_obj.ui_allow_local_only)
    except Exception as exc:
        LOGGER.error(
            "ui.new_client.ui_allow_local_only_failed",
            extra={"error": str(exc)},
        )
        raise ConfigError(
            "Impossibile leggere ui_allow_local_only dalla configurazione.",
        ) from exc


def ui_allow_local_only_enabled() -> bool:
    """Legge (o rilegge) il flag ui_allow_local_only dal settings runtime."""
    try:
        return _resolve_ui_allow_local_only()
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

    layout = None
    try:
        layout = get_ui_workspace_layout(key, require_env=False)
    except Exception:
        layout = None

    if layout is None:
        try:
            layout = WorkspaceLayout.from_slug(slug=key, require_env=False)
        except Exception:
            layout = None

    if layout:
        _LAYOUT_CACHE[key] = layout
    return layout


def _require_layout(slug: str, layout: WorkspaceLayout | None = None) -> WorkspaceLayout:
    candidate = layout if layout is not None else _layout_for_slug(slug)
    if candidate is None:
        raise ConfigError(
            "Workspace layout non disponibile: usa pipeline.workspace_bootstrap per creare o riparare il workspace.",
            slug=slug,
        )
    return candidate


# --------- helper ---------
def _config_dir_client(slug: str, layout: WorkspaceLayout | None = None) -> Path:
    layout = _require_layout(slug, layout)
    return cast(Path, layout.config_path.parent)


def _semantic_dir_client(slug: str, layout: WorkspaceLayout | None = None) -> Path:
    layout = _require_layout(slug, layout)
    return cast(Path, layout.semantic_dir)


def _client_pdf_path(slug: str, layout: WorkspaceLayout | None = None) -> Path:
    layout = _require_layout(slug, layout)
    cfg_dir = layout.config_path.parent
    return cast(Path, layout.vision_pdf or (cfg_dir / "VisionStatement.pdf"))


def _client_vision_yaml_path(slug: str, layout: WorkspaceLayout | None = None) -> Path:
    layout = _require_layout(slug, layout)
    return cast(Path, layout.config_path.parent / "visionstatement.yaml")


def _has_drive_ids(slug: str) -> bool:
    """Ritorna True se nel config del cliente sono presenti gli ID Drive minimi.

    Nota: dopo il provisioning Drive la UI può avere un contesto cache-ato.
    Per garantire determinismo (stato su disco = stato letto), forziamo reload.
    """
    try:
        invalidate_client_context(slug)
        ctx = get_client_context(slug, require_env=False, force_reload=True)
    except Exception:
        return False
    try:
        cfg = get_client_config(ctx) or {}
    except Exception:
        return False
    return bool(cfg.get("drive_raw_folder_id")) and bool(cfg.get("drive_folder_id"))


def _exists_semantic_files(slug: str, layout: WorkspaceLayout | None = None) -> bool:
    sd = _semantic_dir_client(slug, layout=layout)
    return (sd / "semantic_mapping.yaml").exists()


def _mirror_repo_config_into_client(
    slug: str,
    layout: WorkspaceLayout,
    *,
    pdf_bytes: bytes | None = None,
) -> None:
    """Merge del template `config/config.yaml` del repo con la config locale del cliente."""
    if pdf_bytes is not None:
        # Non serve fare nulla qui: il PDF viene salvato direttamente dentro la fase di bootstrap.
        pass
    template_cfg = get_repo_root() / "config" / "config.yaml"
    if not template_cfg.exists():
        LOGGER.warning(
            "ui.new_client.config_template_missing",
            extra={"slug": slug, "template": str(template_cfg)},
        )
        _log_diagnostics(
            slug,
            "warning",
            "ui.new_client.config_template_missing",
            extra={"slug": slug, "template": str(template_cfg)},
            layout=layout,
        )
        raise ConfigError(
            "Template config.yaml del repository non trovato.",
            slug=slug,
            file_path=str(template_cfg),
        )

    client_cfg_dir = _config_dir_client(slug, layout=layout)
    dst_cfg = client_cfg_dir / "config.yaml"
    if not dst_cfg.exists():
        LOGGER.warning(
            "ui.new_client.config_missing",
            extra={"slug": slug, "dst": str(dst_cfg)},
        )
        _log_diagnostics(
            slug,
            "warning",
            "ui.new_client.config_missing",
            extra={"slug": slug, "dst": str(dst_cfg)},
            layout=layout,
        )
        raise ConfigError(
            "Config cliente non trovata al momento del merge.",
            slug=slug,
            file_path=str(dst_cfg),
        )

    try:
        base_cfg = yaml_read(template_cfg.parent, template_cfg) or {}
        current_cfg = yaml_read(client_cfg_dir, dst_cfg) or {}

        if not isinstance(base_cfg, dict):
            base_cfg = {}
        if not isinstance(current_cfg, dict):
            current_cfg = {}

        merged_cfg = deep_merge_dict(base_cfg, current_cfg)
        for key, value in base_cfg.items():
            if key not in merged_cfg:
                merged_cfg[key] = value
        merged_text = yaml.safe_dump(merged_cfg, allow_unicode=True, sort_keys=False)
        safe_write_text(
            dst_cfg,
            merged_text,
            encoding="utf-8",
            atomic=True,
        )

        updated_text = read_text_safe(dst_cfg.parent, dst_cfg, encoding="utf-8")
        missing_lines = []
        for key, value in base_cfg.items():
            if not updated_text.strip().startswith(f"{key}:") and f"{key}:" not in updated_text:
                missing_lines.append(f"{key}: {value}")
        if missing_lines:
            safe_write_text(
                dst_cfg,
                updated_text + "\n" + "\n".join(missing_lines),
                encoding="utf-8",
                atomic=True,
            )
    except Exception as exc:
        # Strict: segnala e interrompe il flusso UI.
        LOGGER.warning(
            "ui.new_client.config_merge_failed",
            extra={"slug": slug, "error": str(exc), "dst": str(dst_cfg)},
        )
        _log_diagnostics(
            slug,
            "warning",
            "ui.new_client.config_merge_failed",
            extra={"slug": slug, "error": str(exc), "dst": str(dst_cfg)},
            layout=layout,
        )
        raise ConfigError(
            "Merge del template config.yaml fallito.",
            slug=slug,
            file_path=str(dst_cfg),
        ) from exc


def _ui_logger() -> logging.Logger:
    """Logger minimale per Vision lato UI."""
    log = cast(logging.Logger, get_structured_logger("ui.vision.new_client"))
    return log


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
        # 2b) Self-check ambiente prima di procedere
        report = run_system_self_check()
        if not report.ok:
            messages = "; ".join(f"{item.name}: {item.message}" for item in report.items if not item.ok)
            raise ConfigError(
                f"Self-check fallito: {messages}",
                slug=s or "-",
                file_path="config/config.yaml",
            )
        try:
            ctx = get_client_context(s, require_env=False)
            with status_guard(
                "Preparo il workspace locale...",
                expanded=True,
                error_label="Errore durante la preparazione del workspace",
            ) as status:
                layout = bootstrap_client_workspace(ctx)
                invalidate_client_context(s)
                ctx = get_client_context(s, require_env=False, force_reload=True)
                if getattr(ctx, "repo_root_dir", None) is None:
                    raise ConfigError(
                        "Context privo di repo_root_dir dopo il bootstrap del workspace.",
                        slug=s,
                    )
                ensure_ownership_file(s, get_repo_root())
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
                cache_key = (s or "").strip().lower()
                if cache_key:
                    _LAYOUT_CACHE[cache_key] = layout
                cfg_dir = layout.config_path.parent if layout.config_path else layout.repo_root_dir / "config"
                _semantic_dir_client(s, layout=layout).mkdir(parents=True, exist_ok=True)
                try:
                    _mirror_repo_config_into_client(s, layout, pdf_bytes=pdf_bytes)
                except ConfigError as exc:
                    _open_error_modal("Errore configurazione", str(exc))
                    st.stop()
                if pdf_bytes:
                    vision_target = cast(
                        Path, ensure_within_and_resolve(layout.repo_root_dir, cfg_dir / "VisionStatement.pdf")
                    )
                    safe_write_bytes(vision_target, pdf_bytes, atomic=True)
                    updates = {"vision_statement_pdf": "config/VisionStatement.pdf"}
                    client_name_value = (name or s).strip()
                    if client_name_value:
                        updates["client_name"] = client_name_value
                    update_config_with_drive_ids(ctx, updates, logger=LOGGER)
                    # Reload immediato dopo scrittura config (pre-Vision) per evitare Context stale.
                    invalidate_client_context(s)
                    ctx = get_client_context(s, require_env=False, force_reload=True)
                    if getattr(ctx, "repo_root_dir", None) is None:
                        raise ConfigError(
                            "Context privo di repo_root_dir dopo la scrittura config pre-Vision.",
                            slug=s,
                        )
                yaml_target = _client_vision_yaml_path(s, layout=layout)
                try:
                    compile_document_to_vision_yaml(_client_pdf_path(s, layout=layout), yaml_target)
                except Exception as exc:
                    LOGGER.warning(
                        "ui.new_client.vision_yaml_generation_failed",
                        extra={"slug": s, "error": str(exc), "pdf": str(_client_pdf_path(s, layout=layout))},
                    )
                    st.error("Generazione Vision fallita. Nessun artefatto epistemico è stato prodotto.")
                    st.stop()
                if status is not None and hasattr(status, "update"):
                    status.update(label="Workspace locale pronto.", state="complete")
                progress.progress(30, text="Workspace locale pronto.")

            # 4) Provisioning minimo su Drive (obbligatorio solo quando disponibile)
            local_only_mode = ui_allow_local_only_enabled()
            strict_mode = is_beta_strict()
            if _ensure_drive_minimal is None:
                if strict_mode:
                    _log_drive_capability_missing(
                        s,
                        phase="init",
                        strict=True,
                        helper_missing=True,
                        ids_missing=False,
                    )
                    st.error(
                        "Provisioning Drive non disponibile in strict mode. "
                        "Installa gli extra `pip install .[drive]` e riprova."
                    )
                    st.stop()
                _log_drive_capability_missing(
                    s,
                    phase="init",
                    strict=False,
                    helper_missing=True,
                    ids_missing=False,
                )
                if local_only_mode:
                    LOGGER.info(
                        "ui.drive.provisioning_skipped",
                        extra={"slug": s, "reason": "helper_unavailable", "local_only": True},
                    )
                    _log_diagnostics(
                        s,
                        "warning",
                        "ui.drive.not_configured_local_only",
                        extra={"slug": s, "phase": "init"},
                        layout=layout,
                    )
                    progress.progress(60, text="Drive in modalità locale (skip provisioning).")
                else:
                    st.error("Provisioning Drive non disponibile. Installa gli extra `pip install .[drive]` e riprova.")
                    st.stop()
            else:
                with status_guard(
                    "Provisioning su Google Drive...",
                    expanded=True,
                    error_label="Errore durante il provisioning Drive",
                ) as status:
                    try:
                        _ensure_drive_minimal(slug=s, client_name=(name or None))
                        if status is not None and hasattr(status, "update"):
                            status.update(label="Drive pronto (cartelle + config aggiornato).", state="complete")
                        progress.progress(60, text="Drive pronto (cartelle + config aggiornato).")

                        # NOTA IMPORTANTE:
                        # La fase di provisioning Drive aggiorna il file config.yaml del cliente su disco
                        # inserendo gli ID drive_* (drive_folder_id, drive_raw_folder_id).
                        # Tuttavia Streamlit e il layer di contesto possono mantenere una versione
                        # cache-ata della configurazione in memoria.
                        #
                        # Senza un reload esplicito, i check successivi (_has_drive_ids)
                        # possono leggere una config obsoleta e fallire erroneamente.
                        #
                        # Forziamo quindi l'invalidazione e il reload del contesto cliente
                        # per garantire coerenza tra stato su disco e stato in memoria.
                        invalidate_client_context(s)
                        ctx = get_client_context(
                            s,
                            require_env=False,
                            force_reload=True,
                        )
                    except Exception as exc:
                        if status is not None and hasattr(status, "update"):
                            status.update(label="Errore durante il provisioning Drive.", state="error")
                        progress.progress(0, text="Errore durante il provisioning Drive.")
                        st.error(
                            "Errore durante il provisioning Drive: "
                            f"{exc}\n\n"
                            "Verifica le variabili .env (es. SERVICE_ACCOUNT_FILE, DRIVE_ID) "
                            "e i permessi dell'account di servizio."
                        )
                        st.stop()

            # 5) Vision
            ui_logger = _ui_logger()
            with status_guard(
                "Eseguo Vision…",
                expanded=True,
                error_label="Errore durante Vision",
            ) as status:
                try:
                    step_progress = st.progress(0, text="Preparazione Vision...")
                    progress.progress(80, text="Eseguo Vision...")
                    run_vision(
                        ctx,
                        slug=s,
                        pdf_path=_client_pdf_path(s, layout=layout),
                        logger=ui_logger,
                        preview_prompt=preview_prompt,
                    )
                    if status is not None and hasattr(status, "update"):
                        status.update(label="Vision completata.", state="complete")
                    step_progress.progress(100, text="Vision completata.")
                    progress.progress(100, text="Vision completata.")
                except Exception as exc:
                    # Mapping unico degli errori (PR-C)
                    try:
                        step_progress.progress(0, text="Errore durante Vision.")
                    except Exception:
                        pass
                    title, body, caption = to_user_message(exc)
                    _log_diagnostics(
                        s,
                        "warning",
                        "ui.vision.error",
                        extra={"slug": s, "type": exc.__class__.__name__, "err": str(exc).splitlines()[:1]},
                        layout=layout,
                    )
                    if status is not None and hasattr(status, "update"):
                        status.update(label=body, state="error")
                    # Se è un gate "forza rigenerazione", offri il pulsante per proseguire
                    if isinstance(exc, ConfigError) and "Forza rigenerazione" in str(exc):

                        def _force_and_retry() -> bool:
                            try:
                                if status is not None and hasattr(status, "update"):
                                    status.update(label="Forzo rigenerazione Vision...", state="running")
                                step_progress.progress(10, text="Forzo rigenerazione Vision...")
                                progress.progress(80, text="Eseguo Vision (forzata)...")
                                run_vision(
                                    ctx,
                                    slug=s,
                                    pdf_path=_client_pdf_path(s, layout=layout),
                                    logger=ui_logger,
                                    preview_prompt=preview_prompt,
                                    force=True,
                                )
                                if status is not None and hasattr(status, "update"):
                                    status.update(label="Vision completata (forzata).", state="complete")
                                step_progress.progress(100, text="Vision completata (forzata).")
                                progress.progress(100, text="Vision completata.")
                                if _exists_semantic_files(s, layout=layout):
                                    set_slug(s)
                                    st.session_state[slug_state_key] = s
                                    st.session_state[phase_state_key] = UI_PHASE_READY_TO_OPEN
                                    st.session_state["client_name"] = name or ""
                                return True
                            except Exception as inner:
                                try:
                                    step_progress.progress(0, text="Errore durante Vision (forzata).")
                                except Exception:
                                    pass
                                st.error(f"Forza rigenerazione fallita: {inner}")
                            return False

                        _open_error_modal(
                            title,
                            body,
                            caption=caption,
                            on_force=_force_and_retry,
                            force_label="Forza rigenerazione e prosegui",
                        )
                        st.stop()
                    else:
                        _open_error_modal(title, body, caption=caption)
                        st.stop()

            # 6) Controllo file semantici e avanzamento fase
            if _exists_semantic_files(s, layout=layout):
                entry = ClientEntry(slug=s, nome=(name or "").strip() or s, stato="nuovo")
                upsert_client(entry)
                set_state(s, "nuovo")

                # Aggiorna contesto UI: mostra Step 2
                set_slug(s)
                st.session_state[slug_state_key] = s
                st.session_state[phase_state_key] = UI_PHASE_READY_TO_OPEN
                st.session_state["client_name"] = name or ""
                st.success("Workspace inizializzato e YAML generati.")
            else:
                st.error("Vision terminata ma i file attesi non sono presenti in semantic/.")
        except (WorkspaceNotFound, WorkspaceLayoutInvalid, WorkspaceLayoutInconsistent) as exc:
            st.error("Impossibile completare il bootstrap: il workspace risultante non è valido o è incoerente.")
            st.caption(
                "Il flusso Nuovo cliente usa "
                "`pipeline.workspace_bootstrap.bootstrap_client_workspace`; verifica lo slug e ricontrolla i dati."
            )
            LOGGER.warning("ui.new_client.bootstrap_failed", extra={"slug": s, "error": str(exc)})
        except Exception as e:  # pragma: no cover
            # Messaggio compatto, diagnosi via pannello dedicato
            st.error(f"Impossibile creare il workspace: {e}")

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
    strict_mode = is_beta_strict()
    if not has_drive_ids and strict_mode:
        _log_drive_capability_missing(
            eff,
            phase="open",
            strict=True,
            helper_missing=_ensure_drive_minimal is None,
            ids_missing=True,
        )
        st.error("Config privo degli ID Drive. In strict mode non è consentito proseguire senza Drive.")
        st.stop()
    if not has_drive_ids:
        _log_drive_capability_missing(
            eff,
            phase="open",
            strict=False,
            helper_missing=_ensure_drive_minimal is None,
            ids_missing=True,
        )
    if not has_drive_ids and not local_only_mode:
        st.warning(
            "Config privo degli ID Drive (drive_folder_id/drive_raw_folder_id). "
            "Ripeti 'Inizializza Workspace' dopo aver configurato le variabili .env e i permessi Drive."
        )

    display_name = st.session_state.get("client_name") or (name or eff)

    if not has_drive_ids and not local_only_mode:
        st.error("Config privo degli ID Drive. Ripeti 'Inizializza Workspace' dopo aver configurato Drive.")
        st.stop()

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
    eff_q = esc_url_component(eff)
    # Navigazione nativa (preferita) con degradazione
    if hasattr(st, "page_link"):
        st.page_link(PagePaths.MANAGE, label="Vai a Gestisci cliente")
    else:
        st.link_button("Vai a Gestisci cliente", url=f"/manage?slug={eff_q}")
