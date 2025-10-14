# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/new_client.py
from __future__ import annotations

import inspect
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, Optional, cast

import streamlit as st

from src.pre_onboarding import ensure_local_workspace_for_ui
from ui.chrome import header, sidebar
from ui.constants import UI_PHASE_INIT, UI_PHASE_PROVISIONED, UI_PHASE_READY_TO_OPEN
from ui.utils import set_slug
from ui.utils.html import esc_url_component

# Vision (provisioning completo: mapping + cartelle_raw)
ProvisionCallable = Callable[..., Any]

if TYPE_CHECKING:
    from src.semantic.vision_provision import provision_from_vision as provision_from_vision
else:
    try:
        from src.semantic.vision_provision import provision_from_vision as _provision_from_vision
    except Exception:  # pragma: no cover
        from semantic.vision_provision import provision_from_vision as _provision_from_vision  # pragma: no cover
    provision_from_vision = cast(ProvisionCallable, _provision_from_vision)

from pipeline.config_utils import merge_client_config_from_template
from pipeline.context import ClientContext
from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import ensure_within_and_resolve, open_for_read
from ui.clients_store import ClientEntry, set_state, upsert_client

BuildDriveCallable = Callable[..., Dict[str, str]]
try:
    from ui.services.drive_runner import build_drive_from_mapping as _build_drive_from_mapping_impl
except Exception:  # pragma: no cover
    _build_drive_from_mapping_impl = None

if _build_drive_from_mapping_impl is not None:
    build_drive_from_mapping: Optional[BuildDriveCallable] = cast(BuildDriveCallable, _build_drive_from_mapping_impl)
else:
    build_drive_from_mapping = None

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


def _config_dir_repo() -> Path:
    return _repo_root() / "config"


def _semantic_dir_repo() -> Path:
    return _repo_root() / "semantic"


def _repo_pdf_path() -> Path:
    return _config_dir_repo() / "VisionStatement.pdf"


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


def _mirror_repo_config_into_client(slug: str, *, pdf_bytes: Optional[bytes]) -> None:
    """
    Porta i file generati/salvati in REPO_ROOT/{config,semantic}
    dentro REPO_ROOT/output/timmy-kb-<slug>/{config,semantic}.
    - Copia config.yaml dalla root nel config del cliente in modo **atomico** e path-safe.
    - Scrive VisionStatement.pdf nel config del cliente:
      * usa pdf_bytes se presenti (upload corrente)
      * altrimenti copia quello della root se esiste (sempre path-safe e atomico).
    """
    repo_cfg = _config_dir_repo()
    cli_cfg = _config_dir_client(slug)
    cli_sem = _semantic_dir_client(slug)

    cli_cfg.mkdir(parents=True, exist_ok=True)
    cli_sem.mkdir(parents=True, exist_ok=True)

    # 1) config.yaml (path-safe + atomic write)
    src_cfg_yaml = ensure_within_and_resolve(repo_cfg, repo_cfg / "config.yaml")
    if Path(src_cfg_yaml).exists():
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
        merge_client_config_from_template(ctx, Path(src_cfg_yaml))

    # 2) VisionStatement.pdf (path-safe + atomic write)
    dst_pdf = ensure_within_and_resolve(cli_cfg, _client_pdf_path(slug))
    if pdf_bytes is not None:
        safe_write_bytes(Path(dst_pdf), pdf_bytes, atomic=True)
    else:
        src_pdf = ensure_within_and_resolve(repo_cfg, _repo_pdf_path())
        if Path(src_pdf).exists():
            # Lettura sicura tramite open_for_read (niente read_bytes diretto)
            with open_for_read(repo_cfg, Path(src_pdf), mode="rb") as fh:
                safe_write_bytes(Path(dst_pdf), fh.read(), atomic=True)


# Registry unificato (SSoT) via ui.clients_store
def _upsert_client_registry(slug: str, client_name: str) -> None:
    """
    Allinea il registro clienti (SSoT) impostando lo stato **pronto**.
    Qui garantiamo la presenza del cliente e lo stato valido
    per il gating della pagina Semantica.
    """
    entry = ClientEntry(slug=slug, nome=(client_name or "").strip() or slug, stato="pronto")
    upsert_client(entry)
    set_state(slug, "pronto")


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
                _mirror_repo_config_into_client(s, pdf_bytes=pdf_bytes)
                _semantic_dir_client(s).mkdir(parents=True, exist_ok=True)
                if status is not None and hasattr(status, "update"):
                    status.update(label="Workspace locale pronto.", state="complete")

            ui_logger = _ui_logger()
            ctx = _UIContext(base_dir=_client_base(s))

            # Loader visivo durante Vision
            with status_guard(
                "Eseguo Vision…",
                expanded=True,
                error_label="Errore durante Vision",
            ) as status:
                try:
                    provision_from_vision(
                        ctx=ctx,
                        logger=ui_logger,
                        slug=s,
                        pdf_path=str(_client_pdf_path(s)),
                    )
                except TypeError:
                    # Ambienti legacy (signature diversa) vengono gestiti
                    # solo se la funzione non accetta i nuovi parametri kw.
                    try:
                        sig = inspect.signature(provision_from_vision)
                    except (ValueError, TypeError):
                        sig = None
                    if sig is not None and {"slug", "pdf_path"}.issubset(sig.parameters):
                        raise
                    provision_from_vision(s, str(_client_pdf_path(s)))
                if status is not None and hasattr(status, "update"):
                    status.update(label="Vision completata.", state="complete")

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

    if st.button("Apri workspace", key="btn_open_ws", width="stretch"):
        display_name = st.session_state.get("client_name") or (name or eff)

        if build_drive_from_mapping is None:
            if UI_ALLOW_LOCAL_ONLY:
                LOGGER.info("ui.wizard.local_fallback", extra={"slug": eff, "local_only": True})
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
    if hasattr(st, "page_link"):
        try:
            st.page_link(
                "src/ui/pages/manage.py",
                label="Vai a Gestisci cliente",
                icon="➡️",
                args={"slug": eff},
            )
        except Exception:
            st.link_button("Vai a Gestisci cliente", f"/manage?slug={eff_q}", width="stretch")
    else:
        st.html(
            f"""
            <a href="/manage?slug={eff_q}" target="_self"
            style="display:inline-block;padding:0.5rem 1rem;border-radius:0.5rem;
                    background:#0f62fe;color:#fff;text-decoration:none;">
            Vai a Gestisci cliente
            </a>
            """
        )
