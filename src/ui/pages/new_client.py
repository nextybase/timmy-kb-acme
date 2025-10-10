# src/ui/pages/new_client.py
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, cast

import streamlit as st
import yaml

from src.pre_onboarding import ensure_local_workspace_for_ui
from ui.chrome import header, sidebar
from ui.utils.query_params import set_slug

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

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

BuildDriveCallable = Callable[..., Dict[str, str]]
try:
    from ui.services.drive_runner import build_drive_from_mapping as _build_drive_from_mapping_impl
except Exception:  # pragma: no cover
    _build_drive_from_mapping_impl = None

if _build_drive_from_mapping_impl is not None:
    build_drive_from_mapping: Optional[BuildDriveCallable] = cast(BuildDriveCallable, _build_drive_from_mapping_impl)
else:
    build_drive_from_mapping = None


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


def _mirror_repo_config_into_client(slug: str, pdf_bytes: Optional[bytes]) -> None:
    """
    Porta i file generati/salvati in REPO_ROOT/{config,semantic}
    dentro REPO_ROOT/output/timmy-kb-<slug>/{config,semantic}.
    - Copia config.yaml dalla root nel config del cliente.
    - Scrive VisionStatement.pdf nel config del cliente:
      * usa pdf_bytes se presenti (upload corrente)
      * altrimenti copia quello della root se esiste.
    """
    repo_cfg = _config_dir_repo()
    cli_cfg = _config_dir_client(slug)
    cli_sem = _semantic_dir_client(slug)

    cli_cfg.mkdir(parents=True, exist_ok=True)
    cli_sem.mkdir(parents=True, exist_ok=True)

    # 1) config.yaml
    src_cfg_yaml = repo_cfg / "config.yaml"
    dst_cfg_yaml = cli_cfg / "config.yaml"
    if src_cfg_yaml.exists():
        shutil.copy2(src_cfg_yaml, dst_cfg_yaml)

    # 2) VisionStatement.pdf
    dst_pdf = _client_pdf_path(slug)
    if pdf_bytes is not None:
        dst_pdf.write_bytes(pdf_bytes)
    else:
        src_pdf = _repo_pdf_path()
        if src_pdf.exists():
            shutil.copy2(src_pdf, dst_pdf)


def _clients_db_file() -> Path:
    repo = _repo_root()
    db_dir = repo / "clients_db"
    db_dir.mkdir(parents=True, exist_ok=True)
    resolved = ensure_within_and_resolve(repo, db_dir / "clients.yaml")
    return cast(Path, resolved)


def _update_clients_registry(slug: str, client_name: str, drive_ids: Dict[str, str], *, logger: logging.Logger) -> None:
    db_file = _clients_db_file()
    try:
        raw = read_text_safe(_repo_root(), db_file, encoding="utf-8")
        data = yaml.safe_load(raw) or {}
    except FileNotFoundError:
        data = {}
    except Exception as exc:  # pragma: no cover - fallback a struttura vuota
        logger.warning(
            "ui.new_client.clients_db.read_error",
            extra={"slug": slug, "path": str(db_file), "error": str(exc)[:200]},
        )
        data = {}

    if not isinstance(data, dict):
        data = {}

    clients = data.get("clients")
    if not isinstance(clients, list):
        clients = []

    drive_payload = {k: str(v) for k, v in (drive_ids or {}).items() if v}
    entry = {
        "slug": slug,
        "nome": (client_name or "").strip() or slug,
        "stato": "provisioned",
        "drive": drive_payload,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    updated = False
    new_clients: list[dict[str, Any]] = []
    for item in clients:
        if isinstance(item, dict) and item.get("slug") == slug:
            merged = dict(item)
            for key, value in entry.items():
                if key == "drive":
                    continue
                merged[key] = value
            existing_drive = merged.get("drive")
            if isinstance(existing_drive, dict):
                merged["drive"] = {**existing_drive, **drive_payload}
            else:
                merged["drive"] = drive_payload
            new_clients.append(merged)
            updated = True
        else:
            new_clients.append(item)

    if not updated:
        new_clients.insert(0, entry)

    data["clients"] = new_clients
    safe_write_text(
        db_file,
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
        atomic=True,
    )
    logger.info(
        "ui.new_client.clients_db.updated",
        extra={"slug": slug, "path": str(db_file), "updated": updated},
    )


# --------- UI ---------
header(None)
sidebar(None)

st.subheader("Nuovo cliente")

# Stato pagina: "init" | "ready_to_open" | "provisioned"
slug_state_key = "new_client.slug"
phase_state_key = "new_client.phase"

current_slug = st.session_state.get(slug_state_key, "")
current_phase = st.session_state.get(phase_state_key, "init")

# Input
slug = st.text_input(
    "Slug cliente",
    placeholder="es. acme-srl",
    key="new_slug",
    value=current_slug or "",
    disabled=(current_phase in ("ready_to_open", "provisioned")),
)
name = st.text_input(
    "Nome cliente (opzionale)",
    placeholder="es. ACME Srl",
    key="new_name",
    disabled=(current_phase in ("ready_to_open", "provisioned")),
)
pdf = st.file_uploader(
    "Vision Statement (PDF)",
    type=["pdf"],
    key="new_vs_pdf",
    disabled=(current_phase in ("ready_to_open", "provisioned")),
    help="Obbligatorio: sarà salvato come config/VisionStatement.pdf",
)

candidate_slug = (slug or "").strip()

# Se la struttura cliente esiste già, passa alla fase 2
if candidate_slug and current_phase == "init":
    if _config_dir_client(candidate_slug).exists():
        st.session_state[slug_state_key] = candidate_slug
        st.session_state[phase_state_key] = "ready_to_open"
        current_slug = candidate_slug
        current_phase = "ready_to_open"

# STEP 1 - Crea workspace + carica PDF (crea e poi "materializza" in output/timmy-kb-<slug>)
if current_phase == "init":
    if st.button("Crea workspace + carica PDF", type="primary", key="btn_init_ws", width="stretch"):
        s = candidate_slug
        if not s:
            st.warning("Inserisci uno slug valido.")
            st.stop()

        if pdf is None:
            st.error("Carica il Vision Statement (PDF) prima di procedere.")
            st.stop()
        pdf_bytes: Optional[bytes] = pdf.read() if pdf is not None else None
        if not pdf_bytes:
            st.error("Il file PDF caricato è vuoto o non leggibile.")
            st.stop()
        try:
            # 1) crea struttura base + salva config.yaml + VisionStatement.pdf
            ensure_local_workspace_for_ui(s, client_name=(name or None), vision_statement_pdf=pdf_bytes)

            # 2) materializza i file nella cartella cliente sotto output/
            _mirror_repo_config_into_client(s, pdf_bytes=pdf_bytes)

            # 3) stato UI
            set_slug(s)  # query param
            st.session_state[slug_state_key] = s
            st.session_state[phase_state_key] = "ready_to_open"
            st.session_state["client_name"] = name or ""
            current_slug = s
            current_phase = "ready_to_open"
            st.success("Workspace creato con successo.")
        except Exception as e:  # pragma: no cover
            st.error(f"Impossibile creare il workspace: {e}")

# Stato
if current_phase in ("ready_to_open", "provisioned") and current_slug:
    st.info(f"Workspace per **{current_slug}** inizializzato.")

# STEP 2 - Apri workspace (Vision + Drive)
if current_phase == "ready_to_open" and current_slug:
    client_pdf = _client_pdf_path(current_slug)
    if not client_pdf.exists():
        st.error(
            "Manca config/VisionStatement.pdf nel workspace cliente. Torna allo step precedente e ricarica il PDF."
        )
        st.stop()

    if st.button("Apri workspace", key="btn_open_ws", width="stretch"):
        try:
            _semantic_dir_client(current_slug).mkdir(parents=True, exist_ok=True)

            ui_logger = _ui_logger()
            with st.status("Eseguo Vision...", expanded=True) as status:
                ctx = _UIContext(base_dir=_client_base(current_slug))
                try:
                    provision_from_vision(
                        ctx=ctx,
                        logger=ui_logger,
                        slug=current_slug,
                        pdf_path=str(client_pdf),
                    )
                except TypeError:
                    # Firme alternative (manteniamo guardia hard sul PDF)
                    provision_from_vision(current_slug, str(client_pdf))
                status.update(label="Vision completata.", state="complete")

            if _exists_semantic_files(current_slug):
                st.session_state[phase_state_key] = "provisioned"
                st.success("YAML generati in `semantic/`. Creo la struttura su Google Drive…")

                # ---- Creazione struttura su Google Drive (post-Vision) ----
                if build_drive_from_mapping is None:
                    st.warning(
                        "Funzionalità Drive non disponibili. "
                        "Installa gli extra: `pip install .[drive]` e imposta "
                        "`DRIVE_ID`/`SERVICE_ACCOUNT_FILE`."
                    )
                else:
                    prog = st.progress(0)
                    info = st.empty()

                    def _cb(step: int, total: int, label: str) -> None:
                        pct = int(step * 100 / max(total, 1))
                        prog.progress(pct)
                        info.markdown(f"{pct}% - {label}")

                    display_name = st.session_state.get("client_name") or (name or current_slug)
                    try:
                        ids = build_drive_from_mapping(
                            slug=current_slug,
                            client_name=display_name,
                            progress=_cb,
                        )
                        _update_clients_registry(current_slug, display_name, ids, logger=ui_logger)
                        st.success(f"Struttura Drive creata: {ids}")
                    except Exception as e:
                        st.error(f"Errore durante la creazione struttura Drive: {e}")
            else:
                st.error(
                    "Vision terminata ma i file attesi non sono presenti in " f"`{_semantic_dir_client(current_slug)}`."
                )
        except Exception as e:  # pragma: no cover
            st.error(f"Errore durante la Vision: {e}")

# STEP 3 - Link finale
if st.session_state.get(phase_state_key) == "provisioned" and current_slug:
    st.markdown(f"[Vai a Gestisci cliente](/manage?slug={current_slug})")
