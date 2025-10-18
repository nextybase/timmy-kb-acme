# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/new_client.py
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, cast

import streamlit as st

from src.pre_onboarding import ensure_local_workspace_for_ui
from ui.chrome import header, sidebar
from ui.constants import UI_PHASE_INIT, UI_PHASE_PROVISIONED, UI_PHASE_READY_TO_OPEN
from ui.utils import set_slug
from ui.utils.html import esc_url_component

try:
    from src.semantic.vision_provision import HaltError
except Exception:  # pragma: no cover
    from semantic.vision_provision import HaltError  # pragma: no cover

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from ui.clients_store import ClientEntry, set_state, upsert_client
from ui.services.vision_provision import run_vision

BuildDriveCallable = Callable[..., Dict[str, str]]
try:
    from ui.services.drive_runner import build_drive_from_mapping as _build_drive_from_mapping_impl
except Exception:  # pragma: no cover
    _build_drive_from_mapping_impl = None

if _build_drive_from_mapping_impl is not None:
    build_drive_from_mapping: Optional[BuildDriveCallable] = cast(BuildDriveCallable, _build_drive_from_mapping_impl)
else:
    build_drive_from_mapping = None

# Bootstrap minimo Drive (prima di Vision)
try:
    from ui.services.drive_runner import ensure_drive_minimal_and_upload_config as _ensure_drive_minimal_impl
except Exception:  # pragma: no cover
    _ensure_drive_minimal_impl = None

if _ensure_drive_minimal_impl is not None:
    ensure_drive_minimal: Optional[BuildDriveCallable] = cast(BuildDriveCallable, _ensure_drive_minimal_impl)
else:
    ensure_drive_minimal = None

UI_ALLOW_LOCAL_ONLY = os.getenv("UI_ALLOW_LOCAL_ONLY", "true").lower() in ("1", "true", "yes")
LOGGER = logging.getLogger("ui.new_client")


# --------- status helper ---------


@contextmanager
def status_guard(label: str, *, error_label: str | None = None, **kwargs: Any) -> Iterator[Any]:
    clean_label = label.rstrip(" .…")
    error_prefix = error_label or (f"Errore durante {clean_label}" if clean_label else "Errore")
    with st.status(label, **kwargs) as status:
        try:
            yield status
        except Exception as exc:
            if status is not None and hasattr(status, "update"):
                status.update(label=f"{error_prefix}: {exc}", state="error")
            raise


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


def _exists_semantic_files(slug: str) -> bool:
    sd = _semantic_dir_client(slug)
    return (sd / "semantic_mapping.yaml").exists() and (sd / "cartelle_raw.yaml").exists()


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
    """Scrive un evento nel log Diagnostica e chiude l'handler per evitare lock (Win compat)."""
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
        if not s:
            st.warning("Inserisci uno slug valido.")
            st.stop()

        if pdf is None:
            st.error("Carica il Vision Statement (PDF) prima di procedere.")
            st.stop()
        pdf_bytes: Optional[bytes] = pdf.getvalue() if pdf is not None else None
        if not pdf_bytes:
            st.error("Il file PDF caricato è vuoto o non leggibile.")
            st.stop()

        try:
            with status_guard(
                "Preparo il workspace locale...",
                expanded=True,
                error_label="Errore durante la preparazione del workspace",
            ) as status:
                ensure_local_workspace_for_ui(s, client_name=(name or None), vision_statement_pdf=pdf_bytes)
                _semantic_dir_client(s).mkdir(parents=True, exist_ok=True)
                if status is not None and hasattr(status, "update"):
                    status.update(label="Workspace locale pronto.", state="complete")

            # Provisioning minimo su Drive (se configurato)
            if ensure_drive_minimal is None and not UI_ALLOW_LOCAL_ONLY:
                _open_error_modal(
                    "Google Drive non configurato",
                    "Funzionalita Drive non disponibili. Installa gli extra `pip install .[drive]` "
                    "e imposta `DRIVE_ID` / `SERVICE_ACCOUNT_FILE`.",
                )
                st.stop()
            if ensure_drive_minimal is not None:
                with status_guard(
                    "Provisiono struttura minima su Drive...",
                    expanded=True,
                    error_label="Errore durante il provisioning Drive",
                ) as status:
                    ensure_drive_minimal(slug=s, client_name=(name or None))
                    if status is not None and hasattr(status, "update"):
                        status.update(label="Struttura minima creata e config caricato.", state="complete")

            ui_logger = _ui_logger()
            ctx = _UIContext(base_dir=_client_base(s))

            # Loader visivo durante Vision
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
                except HaltError as exc:
                    _log_diagnostics(
                        s, "warning", "ui.vision.halt", extra={"slug": s, "err": str(exc).splitlines()[:1]}
                    )
                    if status is not None and hasattr(status, "update"):
                        status.update(label=f"Vision in stato HALT: {exc}", state="error")
                    missing = ""
                    if hasattr(exc, "missing"):
                        details = getattr(exc, "missing")
                        sections = details.get("sections") if isinstance(details, dict) else None
                        if sections:
                            missing = ", ".join(str(item) for item in sections)
                    caption = f"Sezioni mancanti: {missing}" if missing else "Completa il Vision Statement e riprova."
                    _open_error_modal(
                        "Vision HALT",
                        f"Vision interrotta: {exc}",
                        caption=caption,
                    )
                    st.stop()
                except ConfigError as exc:
                    _log_diagnostics(
                        s,
                        "warning",
                        "ui.vision.config_error",
                        extra={"slug": s, "err": str(exc).splitlines()[:1]},
                    )
                    msg = str(exc)
                    lower = msg.lower()
                    if status is not None and hasattr(status, "update"):
                        status.update(label=f"Errore durante Vision: {msg}", state="error")
                    if "sezioni mancanti" in lower or "visionstatement incompleto" in lower:
                        missing = msg.split("-", 1)[-1].strip() if "-" in msg else ""
                        _open_error_modal(
                            "Errore durante Vision",
                            f"Vision interrotta: mancano sezioni obbligatorie → {missing}",
                            caption="Rivedi il PDF e assicurati che tutte le sezioni richieste siano presenti.",
                        )
                    else:
                        _open_error_modal("Errore durante Vision", f"Errore Vision: {msg}")
                    st.stop()
                except Exception as exc:
                    _log_diagnostics(
                        s,
                        "warning",
                        "ui.vision.unhandled",
                        extra={"slug": s, "err": str(exc).splitlines()[:1]},
                    )
                    if status is not None and hasattr(status, "update"):
                        status.update(label=f"Errore durante Vision: {exc}", state="error")
                    _open_error_modal("Errore durante Vision", f"Errore durante Vision: {exc}")
                    st.stop()

            if _exists_semantic_files(s):
                # SSoT: dopo Vision il cliente è "nuovo"
                entry = ClientEntry(slug=s, nome=(name or "").strip() or s, stato="nuovo")
                upsert_client(entry)
                set_state(s, "nuovo")

                # Aggiorna immediatamente contesto UI (fa sparire "Inizializza" e mostra "Apri")
                set_slug(s)
                st.session_state[slug_state_key] = s
                st.session_state[phase_state_key] = UI_PHASE_READY_TO_OPEN
                st.session_state["client_name"] = name or ""
                st.success("Workspace inizializzato e YAML generati.")
                st.rerun()  # <-- forza il rerender per far comparire "Apri workspace"
            else:
                st.error("Vision terminata ma i file attesi non sono presenti in semantic/.")
        except Exception as e:  # pragma: no cover
            # Non mostriamo diagnostica legacy né retry: messaggio compatto
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

    if st.button("Apri workspace", key="btn_open_ws", type="primary", width="stretch"):
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
                st.rerun()
            else:
                st.warning(
                    "Funzionalità Drive non disponibili. Installa gli extra `pip install .[drive]` "
                    "e imposta `DRIVE_ID`/`SERVICE_ACCOUNT_FILE`."
                )
        else:
            try:
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
                st.rerun()  # <-- forza il rerender per mostrare il link finale
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
