# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/new_client.py
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, cast

from ui.pages.registry import PagePaths
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()
import yaml

from pipeline.yaml_utils import yaml_read
from ui.imports import getattr_if_callable, import_first

ensure_local_workspace_for_ui = import_first(
    "timmykb.pre_onboarding",
    "src.pre_onboarding",
    "pre_onboarding",
).ensure_local_workspace_for_ui

from pipeline.context import validate_slug
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.settings import Settings
from ui.chrome import header, sidebar
from ui.clients_store import ClientEntry, set_state, upsert_client
from ui.constants import UI_PHASE_INIT, UI_PHASE_PROVISIONED, UI_PHASE_READY_TO_OPEN
from ui.errors import to_user_message
from ui.utils import set_slug
from ui.utils.context_cache import get_client_context
from ui.utils.html import esc_url_component
from ui.utils.merge import deep_merge_dict
from ui.utils.status import status_guard
from ui.utils.workspace import workspace_root

if TYPE_CHECKING:
    from pipeline.context import ClientContext
else:  # pragma: no cover
    ClientContext = Any  # type: ignore[misc]

_vision_module = import_first(
    "ui.services.vision_provision",
    "timmykb.ui.services.vision_provision",
    "src.ui.services.vision_provision",
)
run_vision = getattr(_vision_module, "run_vision")

BuildDriveCallable = Callable[..., Dict[str, str]]
EnsureDriveCallable = Callable[..., Path]
_drive_runner = import_first(
    "ui.services.drive_runner",
    "timmykb.ui.services.drive_runner",
    "src.ui.services.drive_runner",
)
_build_drive_from_mapping_impl = cast(
    Optional[BuildDriveCallable],
    getattr_if_callable(_drive_runner, "build_drive_from_mapping"),
)
_ensure_drive_minimal_impl = cast(
    Optional[EnsureDriveCallable],
    getattr_if_callable(_drive_runner, "ensure_drive_minimal_and_upload_config"),
)

build_drive_from_mapping: Optional[BuildDriveCallable]
if _build_drive_from_mapping_impl:
    build_drive_from_mapping = _build_drive_from_mapping_impl
else:
    build_drive_from_mapping = None

_ensure_drive_minimal: Optional[EnsureDriveCallable]
if _ensure_drive_minimal_impl:
    _ensure_drive_minimal = _ensure_drive_minimal_impl
else:
    _ensure_drive_minimal = None
from pipeline.config_utils import get_client_config


def _load_repo_settings() -> Optional[Settings]:
    try:
        return Settings.load(_repo_root())
    except Exception:
        return None


def _resolve_ui_allow_local_only() -> bool:
    settings_obj = _load_repo_settings()
    if settings_obj is None:
        return True
    try:
        return bool(settings_obj.ui_allow_local_only)
    except Exception:
        return True


def ui_allow_local_only_enabled() -> bool:
    """Legge (o rilegge) il flag ui_allow_local_only dal settings runtime."""
    return _resolve_ui_allow_local_only()


LOGGER = get_structured_logger("ui.new_client")


# --------- env helpers ---------
def _sanitize_openai_env() -> List[str]:
    """Rimuove variabili legacy OpenAI e avvisa l'utente/telemetria."""
    removed: List[str] = []
    legacy_keys = ("OPENAI_FORCE_HTTPX",)
    for key in legacy_keys:
        if os.environ.pop(key, None) is not None:
            removed.append(key)

    if removed:
        LOGGER.warning("ui.new_client.openai_legacy_env", extra={"removed": removed})
        warn = getattr(st, "warning", None)
        if callable(warn):
            warn(
                "Variabili legacy OpenAI ignorate automaticamente: "
                + ", ".join(removed)
                + ". Aggiorna il tuo .env per rimuoverle.",
            )
    return removed


# --------- helper ---------
def _repo_root() -> Path:
    # new_client.py -> pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


def _client_base(slug: str) -> Path:
    """
    Determina la radice del workspace cliente.
    - Preferisce `workspace_root` (che valida lo slug e ingloba il ClientContext).
    - Fallback: usa la root del repository (override-friendly per i test) mantenendo le guardie.
    """
    fallback_base = _repo_root() / "output" / f"timmy-kb-{slug}"
    base_parent = fallback_base.parent

    candidate: Path
    try:
        candidate = cast(Path, workspace_root(slug))
        # Accettiamo il candidate solo se resta nel perimetro del fallback (copre override repo root).
        candidate = cast(Path, ensure_within_and_resolve(base_parent, candidate))
    except Exception:
        candidate = cast(Path, ensure_within_and_resolve(base_parent, fallback_base))
    return candidate


def _config_dir_client(slug: str) -> Path:
    base = _client_base(slug)
    return cast(Path, ensure_within_and_resolve(base, base / "config"))


def _semantic_dir_client(slug: str) -> Path:
    base = _client_base(slug)
    return cast(Path, ensure_within_and_resolve(base, base / "semantic"))


def _client_pdf_path(slug: str) -> Path:
    cfg_dir = _config_dir_client(slug)
    return cast(Path, ensure_within_and_resolve(cfg_dir, cfg_dir / "VisionStatement.pdf"))


def _has_drive_ids(slug: str) -> bool:
    try:
        ctx = get_client_context(slug, interactive=False, require_env=False)
    except Exception:
        return False
    try:
        cfg = get_client_config(ctx) or {}
    except Exception:
        return False
    return bool(cfg.get("drive_raw_folder_id")) and bool(cfg.get("drive_folder_id"))


def _exists_semantic_files(slug: str) -> bool:
    sd = _semantic_dir_client(slug)
    return (sd / "semantic_mapping.yaml").exists() and (sd / "cartelle_raw.yaml").exists()


def _mirror_repo_config_into_client(slug: str, *, pdf_bytes: bytes | None = None) -> None:
    """Merge del template `config/config.yaml` del repo con la config locale del cliente."""
    if pdf_bytes is not None:
        # Compatibilità: l'eventuale PDF è già stato gestito in `ensure_local_workspace_for_ui`.
        pass
    template_cfg = _repo_root() / "config" / "config.yaml"
    if not template_cfg.exists():
        return

    client_cfg_dir = _config_dir_client(slug)
    dst_cfg = client_cfg_dir / "config.yaml"
    if not dst_cfg.exists():
        return

    try:
        base_cfg = yaml_read(template_cfg.parent, template_cfg) or {}
        current_cfg = yaml_read(client_cfg_dir, dst_cfg) or {}

        merged_cfg = deep_merge_dict(base_cfg, current_cfg)
        safe_write_text(
            dst_cfg,
            yaml.safe_dump(merged_cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
            atomic=True,
        )
    except Exception as exc:
        # Best-effort: segnala l'errore ma non blocca il flusso UI.
        LOGGER.warning(
            "ui.new_client.config_merge_failed",
            extra={"slug": slug, "error": str(exc), "dst": str(dst_cfg)},
        )
        try:
            _log_diagnostics(
                slug,
                "warning",
                "ui.new_client.config_merge_failed",
                extra={"slug": slug, "error": str(exc), "dst": str(dst_cfg)},
            )
        except Exception:
            pass


class _UIContext:
    """Contesto minimo per Vision con base_dir già validato."""

    def __init__(self, slug: str) -> None:
        self.base_dir = _client_base(slug)


def _ui_logger() -> logging.Logger:
    """Logger minimale per Vision lato UI."""
    log = cast(logging.Logger, get_structured_logger("ui.vision.new_client", propagate=False))
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
    - Usa st.dialog se disponibile (Streamlit >= 1.50), altrimenti degrada a messaggio inline.
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

    dialog_builder = getattr(st, "dialog", None)
    if callable(dialog_builder):
        open_modal = dialog_builder(title, width="large")
        modal_runner = open_modal(_modal)
        if callable(modal_runner):
            modal_runner()
        else:
            _modal()
    else:
        _modal()


def _log_diagnostics(slug: str, level: str, message: str, *, extra: Dict[str, Any]) -> None:
    """
    Scrive un evento nel log Diagnostica (WARNING-only by convention) e chiude l'handler
    per evitare lock su Windows. Usiamo sempre livelli >= warning quando invochiamo questa funzione.
    """
    base = _client_base(slug)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("ui.diagnostics", log_file=(base / "logs" / "ui.log"))
    log_method = getattr(logger, level, None)
    if callable(log_method):
        log_method(message, extra=extra)
    else:  # fallback a warning se il livello non esiste
        logger.warning(message, extra=extra)

    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            try:
                handler.flush()
            except Exception:
                pass
            try:
                handler.close()
            except Exception:
                pass
            logger.removeHandler(handler)


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
        # Avviso soft su PDF molto grande (diagnostica)
        try:
            if isinstance(pdf_bytes, (bytes, bytearray)) and len(pdf_bytes) > 20 * 1024 * 1024:
                _log_diagnostics(s, "warning", "ui.new_client.large_pdf", extra={"slug": s, "bytes": len(pdf_bytes)})
        except Exception:
            pass

        try:
            # 3) Bootstrap locale unificato (PR-A): crea struttura + salva PDF + merge template
            with status_guard(
                "Preparo il workspace locale...",
                expanded=True,
                error_label="Errore durante la preparazione del workspace",
            ) as status:
                ensure_local_workspace_for_ui(s, client_name=(name or None), vision_statement_pdf=pdf_bytes)
                _semantic_dir_client(s).mkdir(parents=True, exist_ok=True)
                _mirror_repo_config_into_client(s, pdf_bytes=pdf_bytes)
                if status is not None and hasattr(status, "update"):
                    status.update(label="Workspace locale pronto.", state="complete")
                progress.progress(30, text="Workspace locale pronto.")

            # 4) Provisioning minimo su Drive (obbligatorio solo quando disponibile)
            local_only_mode = ui_allow_local_only_enabled()
            if _ensure_drive_minimal is None:
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
            ctx = _UIContext(slug=s)
            with status_guard(
                "Eseguo Vision…",
                expanded=True,
                error_label="Errore durante Vision",
            ) as status:
                try:
                    _sanitize_openai_env()
                    step_progress = st.progress(0, text="Preparazione Vision...")
                    progress.progress(80, text="Eseguo Vision...")
                    run_vision(
                        ctx,
                        slug=s,
                        pdf_path=_client_pdf_path(s),
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
                                    pdf_path=_client_pdf_path(s),
                                    logger=ui_logger,
                                    preview_prompt=preview_prompt,
                                    force=True,
                                )
                                if status is not None and hasattr(status, "update"):
                                    status.update(label="Vision completata (forzata).", state="complete")
                                step_progress.progress(100, text="Vision completata (forzata).")
                                progress.progress(100, text="Vision completata.")
                                if _exists_semantic_files(s):
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
            if _exists_semantic_files(s):
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
    if not _exists_semantic_files(eff):
        st.error("Per aprire il workspace servono i due YAML in semantic/. Esegui prima 'Inizializza Workspace'.")
        st.stop()

    has_drive_ids = _has_drive_ids(eff)
    local_only_mode = ui_allow_local_only_enabled()
    if not has_drive_ids and not local_only_mode:
        st.warning(
            "Config privo degli ID Drive (drive_folder_id/drive_raw_folder_id). "
            "Ripeti 'Inizializza Workspace' dopo aver configurato le variabili .env e i permessi Drive."
        )

    display_name = st.session_state.get("client_name") or (name or eff)

    if build_drive_from_mapping is None:
        if local_only_mode:
            LOGGER.info("ui.wizard.local_fallback", extra={"slug": eff, "local_only": True})
            _log_diagnostics(
                eff,
                "warning",
                "ui.drive.not_configured_local_only",
                extra={"slug": eff},
            )
            _upsert_client_registry(eff, display_name)
            st.session_state[phase_state_key] = UI_PHASE_PROVISIONED
            st.session_state["client_name"] = display_name
            st.success("Drive non configurato, continuo in locale.")
        else:
            st.warning(
                "Funzionalità Drive non disponibili. Installa gli extra `pip install .[drive]` "
                "e imposta `DRIVE_ID`/`SERVICE_ACCOUNT_FILE`."
            )
    else:
        try:
            if not _has_drive_ids(eff) and not local_only_mode:
                st.error("Config privo degli ID Drive. Ripeti 'Inizializza Workspace' dopo aver configurato Drive.")
                st.stop()

            with status_guard(
                "Provisiono la struttura Drive...",
                expanded=True,
                error_label="Errore durante il provisioning Drive",
            ) as status:

                def _cb(step: int, total: int, label: str) -> None:
                    pct = int(step * 100 / max(total, 1))
                    if status is not None and hasattr(status, "update"):
                        status.update(
                            label=f"Provisiono la struttura Drive... {pct}% - {label}",
                            state="running",
                        )

                _ = build_drive_from_mapping(slug=eff, client_name=display_name, progress=_cb)
                if status is not None and hasattr(status, "update"):
                    status.update(label="Struttura Drive creata correttamente.", state="complete")

            _upsert_client_registry(eff, display_name)
            st.session_state[phase_state_key] = UI_PHASE_PROVISIONED
            st.success("Struttura Drive creata correttamente.")
        except Exception as e:
            st.error(f"Errore durante la creazione struttura Drive: {e}")

# ------------------------------------------------------------------
# STEP 3 - Link finale
# VISIBILE solo quando la fase UI è PROVISIONED
# ------------------------------------------------------------------
if st.session_state.get(phase_state_key) == UI_PHASE_PROVISIONED and (
    st.session_state.get(slug_state_key) or effective_slug
):
    eff = st.session_state.get(slug_state_key) or effective_slug
    eff_q = esc_url_component(eff)
    # Navigazione nativa (preferita) con fallback
    if hasattr(st, "page_link"):
        st.page_link(PagePaths.MANAGE, label="Vai a Gestisci cliente")
    else:
        st.link_button("Vai a Gestisci cliente", url=f"/manage?slug={eff_q}")
