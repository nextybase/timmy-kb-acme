# SPDX-License-Identifier: GPL-3.0-or-later
"""
Pagina Streamlit per modificare la configurazione cliente senza gestire segreti.
- Mostra solo campi mutabili del config YAML (nessun valore *_env).
- Le scritture avvengono tramite helper atomici della pipeline (backup + safe_write_text).
- I riferimenti ai segreti restano in .env: la pagina mostra soltanto il nome della variabile.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import streamlit as st

from pipeline.config_utils import update_config_with_drive_ids
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings
from ui.chrome import render_chrome_then_require
from ui.config_store import MAX_CANDIDATE_LIMIT, MIN_CANDIDATE_LIMIT


def _load_context_and_settings(slug: str) -> Tuple[ClientContext, Settings]:
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False)
    settings_obj = ctx.settings
    if isinstance(settings_obj, Settings):
        return ctx, settings_obj
    repo_root = ctx.repo_root_dir or Path(".")
    config_path = ctx.config_path
    return ctx, Settings.load(repo_root, config_path=config_path, slug=slug)


def _copy_section(data: Dict[str, Any]) -> Dict[str, Any]:
    return dict(data or {})


def main() -> None:
    slug = render_chrome_then_require()
    ctx, settings = _load_context_and_settings(slug)
    data = settings.as_dict()

    st.subheader(f"Config Editor · {slug}")
    st.info(
        "Questa pagina gestisce solo impostazioni applicative. "
        "Eventuali segreti restano in .env e sono referenziati da chiavi *_env.",
        icon="ℹ️",
    )

    vision_cfg = _copy_section(data.get("vision", {}))
    retriever_cfg = _copy_section(data.get("retriever", {}))
    ui_cfg = _copy_section(data.get("ui", {}))

    assistant_env = vision_cfg.get("assistant_id_env") or "N/D"

    saved_flag = st.session_state.pop("config_editor_saved", False)
    if saved_flag:
        st.success("Configurazione aggiornata.")

    with st.form("config_editor_form"):
        st.markdown("### Vision")
        vision_engine = st.text_input(
            "Engine",
            value=str(vision_cfg.get("engine", "")),
            help="Identificativo del motore conversazionale (es. assistant).",
        )
        vision_model = st.text_input(
            "Model",
            value=str(vision_cfg.get("model", "")),
            help="Nome del modello Vision/Assistant (es. gpt-4o-mini-2024-07-18).",
        )
        vision_strict = st.toggle(
            "Strict output",
            value=bool(vision_cfg.get("strict_output", True)),
            help="Se attivo, applica controlli aggiuntivi sugli output del modello.",
        )
        st.caption(f"Assistant ID referenziato via ENV: `{assistant_env}` (non modificabile qui).")

        st.markdown("---")
        st.markdown("### Retriever")
        candidate_limit = st.number_input(
            "Candidate limit",
            min_value=MIN_CANDIDATE_LIMIT,
            max_value=MAX_CANDIDATE_LIMIT,
            value=int(retriever_cfg.get("candidate_limit", MIN_CANDIDATE_LIMIT)),
            step=500,
            help="Numero massimo di candidati restituiti dal retriever.",
        )
        latency_budget = st.number_input(
            "Budget latenza (ms)",
            min_value=0,
            max_value=2000,
            value=int(retriever_cfg.get("latency_budget_ms", 0)),
            step=50,
            help="Tempo massimo (in millisecondi) consentito per una ricerca.",
        )
        auto_by_budget = st.toggle(
            "Auto per budget",
            value=bool(retriever_cfg.get("auto_by_budget", retriever_cfg.get("auto", False))),
            help="Se attivo, riduce automaticamente il numero di candidati in base al budget di latenza.",
        )

        st.markdown("---")
        st.markdown("### Logging")
        log_file_path = st.text_input(
            "Percorso file log",
            value=str(data.get("log_file_path", "logs/onboarding.log")),
            help="Percorso relativo al workspace cliente per il file di log.",
        )
        log_max_bytes = st.number_input(
            "Log max bytes",
            min_value=1024,
            max_value=50 * 1024 * 1024,
            value=int(data.get("log_max_bytes", 1_048_576)),
            step=1024,
            help="Dimensione massima del file di log prima del rollover.",
        )
        log_backup_count = st.number_input(
            "Numero backup log",
            min_value=0,
            max_value=50,
            value=int(data.get("log_backup_count", 3)),
            step=1,
            help="Numero di file di log di backup mantenuti.",
        )

        st.markdown("---")
        st.markdown("### UI e Debug")
        skip_preflight = st.toggle(
            "Salta preflight iniziale",
            value=bool(ui_cfg.get("skip_preflight", data.get("skip_preflight", False))),
            help="Persistente: memorizza ui.skip_preflight nel config del cliente.",
        )
        debug_mode = st.toggle(
            "Modalità debug",
            value=bool(data.get("debug", False)),
            help="Abilita flag di debug per i servizi client.",
        )
        gitbook_image = st.text_input(
            "Immagine Docker GitBook/HonKit",
            value=str(data.get("gitbook_image", "")),
            help="Repository immagine Docker utilizzata per la preview HonKit.",
        )
        gitbook_workspace = st.text_input(
            "Workspace GitBook",
            value=str(data.get("gitbook_workspace", "")),
            help="Nome workspace GitBook (se applicabile).",
        )

        submitted = st.form_submit_button("Salva modifiche", type="primary")

    if not submitted:
        return

    validation_errors = []
    if not vision_engine.strip():
        validation_errors.append("L'engine Vision non può essere vuoto.")
    if not vision_model.strip():
        validation_errors.append("Il modello Vision è obbligatorio.")
    if validation_errors:
        for err in validation_errors:
            st.error(err)
        return

    updates: Dict[str, Any] = {}

    new_vision = _copy_section(vision_cfg)
    new_vision["engine"] = vision_engine.strip()
    new_vision["model"] = vision_model.strip()
    new_vision["strict_output"] = bool(vision_strict)
    updates["vision"] = new_vision

    new_retriever = _copy_section(retriever_cfg)
    new_retriever["candidate_limit"] = int(candidate_limit)
    new_retriever["latency_budget_ms"] = int(latency_budget)
    new_retriever["budget_ms"] = int(latency_budget)
    new_retriever["auto_by_budget"] = bool(auto_by_budget)
    new_retriever["auto"] = bool(auto_by_budget)
    updates["retriever"] = new_retriever

    updates["log_file_path"] = log_file_path.strip()
    updates["log_max_bytes"] = int(log_max_bytes)
    updates["log_backup_count"] = int(log_backup_count)
    updates["debug"] = bool(debug_mode)

    new_ui = _copy_section(ui_cfg)
    new_ui["skip_preflight"] = bool(skip_preflight)
    updates["ui"] = new_ui

    updates["gitbook_image"] = gitbook_image.strip()
    updates["gitbook_workspace"] = gitbook_workspace.strip()

    try:
        update_config_with_drive_ids(ctx, updates, logger=ctx.logger)
    except ConfigError as exc:
        st.error(f"Impossibile salvare la configurazione: {exc}")
        return
    except Exception as exc:
        st.error(f"Errore imprevisto durante il salvataggio: {exc}")
        return

    st.session_state["config_editor_saved"] = True
    try:
        st.rerun()
    except Exception:
        pass


if __name__ == "__main__":
    main()
