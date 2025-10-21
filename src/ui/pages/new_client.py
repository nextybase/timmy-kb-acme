# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/new_client.py
from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

import streamlit as st
import yaml

try:
    from timmykb.pre_onboarding import ensure_local_workspace_for_ui
except ImportError:
    try:
        from src.pre_onboarding import ensure_local_workspace_for_ui
    except ImportError:  # pragma: no cover
        from pre_onboarding import ensure_local_workspace_for_ui

from ui.chrome import header, sidebar
from ui.constants import UI_PHASE_INIT, UI_PHASE_PROVISIONED, UI_PHASE_READY_TO_OPEN
from ui.errors import to_user_message
from ui.utils import set_slug
from ui.utils.html import esc_url_component
from ui.utils.status import status_guard

try:
    pass
except Exception:  # pragma: no cover
    pass  # pragma: no cover

from pipeline.context import ClientContext, validate_slug
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import read_text_safe
from ui.clients_store import ClientEntry, set_state, upsert_client

_vision_module = None
for _vision_mod_name in (
    "ui.services.vision_provision",
    "timmykb.ui.services.vision_provision",
    "src.ui.services.vision_provision",
):
    try:
        _vision_module = importlib.import_module(_vision_mod_name)
        break
    except ImportError:
        continue

if _vision_module is None:
    raise ImportError("Impossibile importare ui.services.vision_provision")

run_vision = getattr(_vision_module, "run_vision")

BuildDriveCallable = Callable[..., Dict[str, str]]
EnsureDriveCallable = Callable[..., Path]
_build_drive_from_mapping_impl: Optional[BuildDriveCallable] = None
_ensure_drive_minimal_impl: Optional[EnsureDriveCallable] = None

for _mod in ("ui.services.drive_runner", "timmykb.ui.services.drive_runner", "src.ui.services.drive_runner"):
    try:
        _drive_runner = importlib.import_module(_mod)
    except ImportError:
        continue
    _build_candidate = getattr(_drive_runner, "build_drive_from_mapping", None)
    _ensure_candidate = getattr(_drive_runner, "ensure_drive_minimal_and_upload_config", None)
    if _mod == "ui.services.drive_runner":
        if callable(_build_candidate):
            _build_drive_from_mapping_impl = cast(BuildDriveCallable, _build_candidate)
        if callable(_ensure_candidate):
            _ensure_drive_minimal_impl = cast(EnsureDriveCallable, _ensure_candidate)
        break
    if _build_drive_from_mapping_impl is None and callable(_build_candidate):
        _build_drive_from_mapping_impl = cast(BuildDriveCallable, _build_candidate)
    if _ensure_drive_minimal_impl is None and callable(_ensure_candidate):
        _ensure_drive_minimal_impl = cast(EnsureDriveCallable, _ensure_candidate)
    if _build_drive_from_mapping_impl is not None and _ensure_drive_minimal_impl is not None:
        break

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

UI_ALLOW_LOCAL_ONLY = os.getenv("UI_ALLOW_LOCAL_ONLY", "true").lower() in ("1", "true", "yes")
LOGGER = logging.getLogger("ui.new_client")


# --------- helper ---------
def _repo_root() -> Path:
    # new_client.py -> pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


def _client_base(slug: str) -> Path:
    return _repo_root() / "output" / f"timmy-kb-{slug}"


def _config_dir_client(slug: str) -> Path:
    return _client_base(slug) / "config"


def _semantic_dir_client(slug: str) -> Path:
    return _client_base(slug) / "semantic"


def _client_pdf_path(slug: str) -> Path:
    return _config_dir_client(slug) / "VisionStatement.pdf"


def _has_drive_ids(slug: str) -> bool:
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False)
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
        repo_payload = read_text_safe(template_cfg.parent, template_cfg, encoding="utf-8")
        base_cfg = yaml.safe_load(repo_payload) or {}

        client_payload = read_text_safe(client_cfg_dir, dst_cfg, encoding="utf-8")
        current_cfg = yaml.safe_load(client_payload) or {}

        merged_cfg = {**base_cfg, **current_cfg}
        safe_write_text(
            dst_cfg,
            yaml.safe_dump(merged_cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
            atomic=True,
        )
    except Exception:
        # Best-effort: eventuali errori non devono bloccare il flusso UI.
        pass


class _UIContext:
    """Contesto minimo per Vision: solo .base_dir (per-cliente)."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir


def _ui_logger() -> logging.Logger:
    """Logger minimale per Vision lato UI."""
    log = logging.getLogger("ui.vision.new_client")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def _open_error_modal(title: str, body: str, *, caption: str | None = None) -> None:
    """
    Mostra un modal di errore con bottone 'Annulla'.
    - Usa st.dialog se disponibile (Streamlit >= 1.50), altrimenti degrada a messaggio inline.
    - Alla pressione di 'Annulla' il modal si chiude (ritorno semplice).
    """

    def _modal() -> None:
        st.error(body)
        if caption:
            st.caption(caption)
        if st.button("Annulla", type="secondary", width="stretch"):
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

            # 4) Provisioning minimo su Drive (obbligatorio solo quando disponibile)
            if _ensure_drive_minimal is None:
                if UI_ALLOW_LOCAL_ONLY:
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
                    except Exception as exc:
                        if status is not None and hasattr(status, "update"):
                            status.update(label="Errore durante il provisioning Drive.", state="error")
                        st.error(
                            "Errore durante il provisioning Drive: "
                            f"{exc}\n\n"
                            "Verifica le variabili .env (es. SERVICE_ACCOUNT_FILE, DRIVE_ID) "
                            "e i permessi dell'account di servizio."
                        )
                        st.stop()

            # 5) Vision
            ui_logger = _ui_logger()
            ctx = _UIContext(base_dir=_client_base(s))
            with status_guard(
                "Eseguo Vision…",
                expanded=True,
                error_label="Errore durante Vision",
            ) as status:
                try:
                    run_vision(
                        ctx,
                        slug=s,
                        pdf_path=_client_pdf_path(s),
                        logger=ui_logger,
                    )
                    if status is not None and hasattr(status, "update"):
                        status.update(label="Vision completata.", state="complete")
                except Exception as exc:
                    # Mapping unico degli errori (PR-C)
                    title, body, caption = to_user_message(exc)
                    _log_diagnostics(
                        s,
                        "warning",
                        "ui.vision.error",
                        extra={"slug": s, "type": exc.__class__.__name__, "err": str(exc).splitlines()[:1]},
                    )
                    if status is not None and hasattr(status, "update"):
                        status.update(label=body, state="error")
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
    if not has_drive_ids and not UI_ALLOW_LOCAL_ONLY:
        st.warning(
            "Config privo degli ID Drive (drive_folder_id/drive_raw_folder_id). "
            "Ripeti 'Inizializza Workspace' dopo aver configurato le variabili .env e i permessi Drive."
        )

    if st.button(
        "Apri workspace",
        key="btn_open_ws",
        type="primary",
        width="stretch",
        disabled=(not has_drive_ids and not UI_ALLOW_LOCAL_ONLY),
    ):
        display_name = st.session_state.get("client_name") or (name or eff)

        if build_drive_from_mapping is None:
            if UI_ALLOW_LOCAL_ONLY:
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
                if not _has_drive_ids(eff) and not UI_ALLOW_LOCAL_ONLY:
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
    st.html(
        f"""
        <div style="width:100%;">
          <a href="/manage?slug={eff_q}" target="_self"
             style="
               display:block;text-align:center;
               padding:0.6rem 1rem;border-radius:0.5rem;
               background:#0f62fe;color:#fff;text-decoration:none;
               font-weight:600;">
            ➡️&nbsp;Vai a Gestisci cliente
          </a>
        </div>
        """
    )
