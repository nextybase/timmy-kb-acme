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

from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()

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


def _extract_sections(data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    return (
        _copy_section(data.get("vision", {})),
        _copy_section(data.get("retriever", {})),
        _copy_section(data.get("ui", {})),
    )


def render_sidebar(slug: str, assistant_env: str, *, st_module: Any | None = None) -> None:
    st_mod = st_module or get_streamlit()
    sidebar = getattr(st_mod, "sidebar", st_mod)
    sidebar.header("Workspace")
    sidebar.markdown(f"- **Slug:** `{slug}`")
    sidebar.markdown(f"- **Assistant ENV:** `{assistant_env}`")


def render_body(
    *,
    st_module: Any | None,
    data: Dict[str, Any],
    vision_cfg: Dict[str, Any],
    retriever_cfg: Dict[str, Any],
    ui_cfg: Dict[str, Any],
    assistant_env: str,
) -> Tuple[bool, Dict[str, Any]]:
    st_mod = st_module or get_streamlit()

    with st_mod.form("config_editor_form"):
        st_mod.markdown("### Vision")
        vision_engine = st_mod.text_input(
            "Engine",
            value=str(vision_cfg.get("engine", "")),
            help="Identificativo del motore conversazionale (es. assistant).",
        )
        vision_model = st_mod.text_input(
            "Model",
            value=str(vision_cfg.get("model", "")),
            help="Nome del modello Vision/Assistant (es. gpt-4o-mini-2024-07-18).",
        )
        vision_strict = st_mod.toggle(
            "Strict output",
            value=bool(vision_cfg.get("strict_output", True)),
            help="Se attivo, applica controlli aggiuntivi sugli output del modello.",
        )
        st_mod.caption(f"Assistant ID referenziato via ENV: `{assistant_env}` (non modificabile qui).")

        st_mod.markdown("---")
        st_mod.markdown("### Retriever")
        candidate_limit = st_mod.number_input(
            "Candidate limit",
            min_value=MIN_CANDIDATE_LIMIT,
            max_value=MAX_CANDIDATE_LIMIT,
            value=int(retriever_cfg.get("candidate_limit", MIN_CANDIDATE_LIMIT)),
            step=500,
            help="Numero massimo di candidati restituiti dal retriever.",
        )
        latency_budget = st_mod.number_input(
            "Budget latenza (ms)",
            min_value=0,
            max_value=2000,
            value=int(retriever_cfg.get("latency_budget_ms", 0)),
            step=50,
            help="Tempo massimo (in millisecondi) consentito per una ricerca.",
        )
        auto_by_budget = st_mod.toggle(
            "Auto per budget",
            value=bool(retriever_cfg.get("auto_by_budget", retriever_cfg.get("auto", False))),
            help="Se attivo, riduce automaticamente il numero di candidati in base al budget di latenza.",
        )

        st_mod.markdown("---")
        st_mod.markdown("### Logging")
        log_file_path = st_mod.text_input(
            "Percorso file log",
            value=str(data.get("log_file_path", "logs/onboarding.log")),
            help="Percorso relativo al workspace cliente per il file di log.",
        )
        log_max_bytes = st_mod.number_input(
            "Log max bytes",
            min_value=1024,
            max_value=50 * 1024 * 1024,
            value=int(data.get("log_max_bytes", 1_048_576)),
            step=1024,
            help="Dimensione massima del file di log prima del rollover.",
        )
        log_backup_count = st_mod.number_input(
            "Numero backup log",
            min_value=0,
            max_value=50,
            value=int(data.get("log_backup_count", 3)),
            step=1,
            help="Numero di file di log di backup mantenuti.",
        )

        st_mod.markdown("---")
        st_mod.markdown("### UI e Debug")
        skip_preflight = st_mod.toggle(
            "Salta preflight iniziale",
            value=bool(ui_cfg.get("skip_preflight", data.get("skip_preflight", False))),
            help="Persistente: memorizza ui.skip_preflight nel config del cliente.",
        )
        debug_mode = st_mod.toggle(
            "Modalità debug",
            value=bool(data.get("debug", False)),
            help="Abilita flag di debug per i servizi client.",
        )
        gitbook_image = st_mod.text_input(
            "Immagine Docker GitBook/HonKit",
            value=str(data.get("gitbook_image", "")),
            help="Repository immagine Docker utilizzata per la preview HonKit.",
        )
        gitbook_workspace = st_mod.text_input(
            "Workspace GitBook",
            value=str(data.get("gitbook_workspace", "")),
            help="Nome workspace GitBook (se applicabile).",
        )

        submitted = st_mod.form_submit_button("Salva modifiche", type="primary")

    return submitted, {
        "vision_engine": vision_engine,
        "vision_model": vision_model,
        "vision_strict": bool(vision_strict),
        "candidate_limit": int(candidate_limit),
        "latency_budget": int(latency_budget),
        "auto_by_budget": bool(auto_by_budget),
        "log_file_path": log_file_path,
        "log_max_bytes": int(log_max_bytes),
        "log_backup_count": int(log_backup_count),
        "skip_preflight": bool(skip_preflight),
        "debug_mode": bool(debug_mode),
        "gitbook_image": gitbook_image,
        "gitbook_workspace": gitbook_workspace,
    }


def _validate_form(values: Dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(values["vision_engine"]).strip():
        errors.append("L'engine Vision non può essere vuoto.")
    if not str(values["vision_model"]).strip():
        errors.append("Il modello Vision è obbligatorio.")
    return errors


def _build_updates(
    *,
    vision_cfg: Dict[str, Any],
    retriever_cfg: Dict[str, Any],
    ui_cfg: Dict[str, Any],
    data: Dict[str, Any],
    values: Dict[str, Any],
) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}

    new_vision = _copy_section(vision_cfg)
    new_vision["engine"] = str(values["vision_engine"]).strip()
    new_vision["model"] = str(values["vision_model"]).strip()
    new_vision["strict_output"] = bool(values["vision_strict"])
    updates["vision"] = new_vision

    new_retriever = _copy_section(retriever_cfg)
    new_retriever["candidate_limit"] = int(values["candidate_limit"])
    latency_budget = int(values["latency_budget"])
    new_retriever["latency_budget_ms"] = latency_budget
    new_retriever["budget_ms"] = latency_budget
    auto_by_budget = bool(values["auto_by_budget"])
    new_retriever["auto_by_budget"] = auto_by_budget
    new_retriever["auto"] = auto_by_budget
    updates["retriever"] = new_retriever

    updates["log_file_path"] = str(values["log_file_path"]).strip()
    updates["log_max_bytes"] = int(values["log_max_bytes"])
    updates["log_backup_count"] = int(values["log_backup_count"])
    updates["debug"] = bool(values["debug_mode"])

    new_ui = _copy_section(ui_cfg)
    new_ui["skip_preflight"] = bool(values["skip_preflight"])
    updates["ui"] = new_ui

    updates["gitbook_image"] = str(values["gitbook_image"]).strip()
    updates["gitbook_workspace"] = str(values["gitbook_workspace"]).strip()
    updates.setdefault("skip_preflight", bool(data.get("skip_preflight", False)))

    return updates


def handle_actions(
    ctx: ClientContext,
    *,
    st_module: Any | None,
    data: Dict[str, Any],
    vision_cfg: Dict[str, Any],
    retriever_cfg: Dict[str, Any],
    ui_cfg: Dict[str, Any],
    form_values: Dict[str, Any],
) -> bool:
    st_mod = st_module or get_streamlit()

    validation_errors = _validate_form(form_values)
    if validation_errors:
        for err in validation_errors:
            st_mod.error(err)
        return False

    updates = _build_updates(
        vision_cfg=vision_cfg,
        retriever_cfg=retriever_cfg,
        ui_cfg=ui_cfg,
        data=data,
        values=form_values,
    )

    try:
        update_config_with_drive_ids(ctx, updates, logger=ctx.logger)
    except ConfigError as exc:
        st_mod.error(f"Impossibile salvare la configurazione: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - imprevisti
        st_mod.error(f"Errore imprevisto durante il salvataggio: {exc}")
        return False

    st_mod.session_state["config_editor_saved"] = True
    try:
        st_mod.rerun()
    except Exception:
        pass
    return True


def main() -> None:
    slug = render_chrome_then_require()
    ctx, settings = _load_context_and_settings(slug)
    data = settings.as_dict()

    st.subheader(f"Config Editor �� {slug}")
    st.info(
        "Questa pagina gestisce solo impostazioni applicative. "
        "Eventuali segreti restano in .env e sono referenziati da chiavi *_env.",
        icon="ℹ️",
    )

    vision_cfg, retriever_cfg, ui_cfg = _extract_sections(data)
    assistant_env = vision_cfg.get("assistant_id_env") or "N/D"

    render_sidebar(slug, assistant_env, st_module=st)

    saved_flag = st.session_state.pop("config_editor_saved", False)
    if saved_flag:
        st.success("Configurazione aggiornata.")

    submitted, form_values = render_body(
        st_module=st,
        data=data,
        vision_cfg=vision_cfg,
        retriever_cfg=retriever_cfg,
        ui_cfg=ui_cfg,
        assistant_env=assistant_env,
    )

    if not submitted:
        return

    handle_actions(
        ctx,
        st_module=st,
        data=data,
        vision_cfg=vision_cfg,
        retriever_cfg=retriever_cfg,
        ui_cfg=ui_cfg,
        form_values=form_values,
    )


if __name__ == "__main__":
    main()
