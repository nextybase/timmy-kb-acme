# src/ui/pages/new_client.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

import streamlit as st

from src.pre_onboarding import ensure_local_workspace_for_ui
from ui.chrome import header, sidebar
from ui.utils.query_params import set_slug

# Vision (provisioning completo: mapping + cartelle_raw)
# Import deterministico con percorso "src"; se il tuo layout usa un alias diverso, adatta qui.
try:
    from src.semantic.vision_provision import provision_from_vision  # type: ignore
except Exception:  # pragma: no cover
    # fallback opzionale se il modulo è referenziato senza prefisso "src"
    from semantic.vision_provision import provision_from_vision  # type: ignore


# --------- helper locali ---------
def _repo_root() -> Path:
    # new_client.py -> pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


def _client_base(slug: str) -> Path:
    # Struttura standard: output/timmy-kb-<slug>/
    return _repo_root() / "output" / f"timmy-kb-{slug}"


def _config_dir(slug: str) -> Path:
    return _client_base(slug) / "config"


def _semantic_dir(slug: str) -> Path:
    return _client_base(slug) / "semantic"


def _pdf_path(slug: str) -> Path:
    return _config_dir(slug) / "VisionStatement.pdf"


def _exists_workspace(slug: str) -> bool:
    return _config_dir(slug).exists()


def _exists_semantic_files(slug: str) -> bool:
    sd = _semantic_dir(slug)
    return (sd / "semantic_mapping.yaml").exists() and (sd / "cartelle_raw.yaml").exists()


# --------- UI ---------
header(None)
sidebar(None)

st.subheader("Nuovo cliente")

# Stato di pagina (non usare experimental): fase: "init" | "ready_to_open" | "provisioned"
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
    "Vision Statement (PDF, opzionale)",
    type=["pdf"],
    key="new_vs_pdf",
    disabled=(current_phase in ("ready_to_open", "provisioned")),
)

candidate_slug = (slug or "").strip()

# Se l'utente digita uno slug che risulta già inizializzato, adegua automaticamente la fase.
if candidate_slug and _exists_workspace(candidate_slug) and current_phase == "init":
    st.session_state[slug_state_key] = candidate_slug
    st.session_state[phase_state_key] = "ready_to_open"
    current_slug = candidate_slug
    current_phase = "ready_to_open"

# STEP 1 — Inizializza workspace
if current_phase == "init":
    if st.button("Inizializza workspace", type="primary", key="btn_init_ws", width="stretch"):
        s = candidate_slug
        if not s:
            st.warning("Inserisci uno slug valido.")
            st.stop()

        pdf_bytes: Optional[bytes] = pdf.read() if pdf is not None else None
        try:
            # Crea struttura base + salva config.yaml + (opzionale) VisionStatement.pdf
            ensure_local_workspace_for_ui(s, client_name=(name or None), vision_statement_pdf=pdf_bytes)
            set_slug(s)  # imposta slug nei query params
            st.session_state[slug_state_key] = s
            st.session_state[phase_state_key] = "ready_to_open"
            current_slug = s
            current_phase = "ready_to_open"
            st.success("Workspace creato con successo.")
        except Exception as e:  # pragma: no cover
            st.error(f"Impossibile creare il workspace: {e}")

# Informazione stato
if current_phase in ("ready_to_open", "provisioned") and current_slug:
    st.info(f"Workspace per **{current_slug}** inizializzato.")

# STEP 2 — Apri workspace (esegue Vision: genera YAML in semantic/)
if current_phase == "ready_to_open" and current_slug:
    vs_pdf = _pdf_path(current_slug)
    if not vs_pdf.exists():
        st.warning("Nessun VisionStatement.pdf trovato in config/. Procedo con la Vision anche senza PDF.")

    if st.button("Apri workspace", key="btn_open_ws", width="stretch"):
        try:
            # Assicura cartella semantic/
            _semantic_dir(current_slug).mkdir(parents=True, exist_ok=True)

            # Esecuzione Vision con progress visibile
            with st.status("Eseguo Vision…", expanded=True) as status:
                # Preferiamo passare pdf_path se esiste, ma tolleriamo signature diverse
                try:
                    provision_from_vision(  # type: ignore
                        ctx=None,
                        logger=None,
                        slug=current_slug,
                        pdf_path=str(vs_pdf) if vs_pdf.exists() else None,
                    )
                except TypeError:
                    # Alcune varianti accettano una firma più semplice
                    if vs_pdf.exists():
                        provision_from_vision(current_slug, str(vs_pdf))  # type: ignore
                    else:
                        provision_from_vision(current_slug)  # type: ignore
                status.update(label="Vision completata.", state="complete")

            # Verifica file generati
            if _exists_semantic_files(current_slug):
                st.session_state[phase_state_key] = "provisioned"
                st.success("Workspace completato: YAML generati in `semantic/`.")
            else:
                st.error("Vision terminata ma i file attesi non sono presenti in `semantic/`.")
        except Exception as e:  # pragma: no cover
            st.error(f"Errore durante la Vision: {e}")

# STEP 3 — Link finale a Gestisci cliente (solo se provisioning completato)
if st.session_state.get(phase_state_key) == "provisioned" and current_slug:
    # Link deterministico alla pagina manage con slug propagato
    st.link_button("Vai a Gestisci cliente", url=f"/manage?slug={current_slug}", key="btn_go_manage")
