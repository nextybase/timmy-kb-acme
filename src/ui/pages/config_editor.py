# SPDX-License-Identifier: GPL-3.0-or-later
"""
Pagina Streamlit per configurare un workspace cliente.

- Modifica i campi mutabili del config YAML (nessun valore *_env).
- Le scritture avvengono tramite helper atomici della pipeline (backup + safe_write_text).
- I riferimenti ai segreti restano in .env: la pagina mostra soltanto il nome della variabile.
- Espone in più:
  - il tuning runtime del retriever (ui.config_store),
  - gli editor YAML semantici (semantic_mapping/cartelle_raw).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Tuple

from ui.types import StreamlitLike
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st: StreamlitLike = get_streamlit()

from pipeline.config_utils import update_config_with_drive_ids
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_all as get_clients
from ui.config_store import MAX_CANDIDATE_LIMIT, MIN_CANDIDATE_LIMIT, get_retriever_settings, set_retriever_settings
from ui.manage import cleanup as cleanup_component
from ui.utils import set_slug
from ui.utils.context_cache import get_client_context
from ui.utils.workspace import get_ui_workspace_layout, resolve_raw_dir

if TYPE_CHECKING:
    from pipeline.context import ClientContext
else:  # pragma: no cover
    ClientContext = Any  # type: ignore[misc]


# ---------- helpers config ----------
def _load_context_and_settings(slug: str) -> Tuple[ClientContext, Settings]:
    ctx = get_client_context(slug, require_env=False)
    settings_obj = ctx.settings
    if isinstance(settings_obj, Settings):
        return ctx, settings_obj
    repo_root = ctx.repo_root_dir or Path(".")
    config_path = ctx.config_path
    return ctx, Settings.load(repo_root, config_path=config_path, slug=slug)


def _copy_section(data: Dict[str, Any]) -> Dict[str, Any]:
    return dict(data or {})


def _extract_sections(data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    vision = _copy_section(data.get("vision", {}))
    retriever = _copy_section(data.get("retriever", {}))
    throttle = _copy_section(retriever.get("throttle", {}))
    retriever["throttle"] = throttle
    ui = _copy_section(data.get("ui", {}))
    return vision, retriever, ui


def render_sidebar(slug: str, assistant_env: str, *, st_module: StreamlitLike | None = None) -> None:
    st_mod = st_module or get_streamlit()
    sidebar = getattr(st_mod, "sidebar", st_mod)
    sidebar.header("Workspace")
    sidebar.markdown(f"- **Slug:** `{slug}`")
    sidebar.markdown(f"- **Assistant ENV:** `{assistant_env}`")


def render_body(
    *,
    st_module: StreamlitLike | None,
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
        st_mod.markdown("### Retriever (config YAML)")
        throttle_cfg = retriever_cfg.get("throttle", {})
        candidate_limit = st_mod.number_input(
            "Candidate limit (config)",
            min_value=MIN_CANDIDATE_LIMIT,
            max_value=MAX_CANDIDATE_LIMIT,
            value=int(throttle_cfg.get("candidate_limit", MIN_CANDIDATE_LIMIT)),
            step=500,
            key="Candidate limit",
            help="Valore base nel config per il numero massimo di candidati restituiti dal retriever.",
        )
        latency_budget = st_mod.number_input(
            "Budget latenza (ms, config)",
            min_value=0,
            max_value=2000,
            value=int(throttle_cfg.get("latency_budget_ms", 0)),
            step=50,
            key="Budget latenza (ms)",
            help="Tempo massimo (in millisecondi) nel config per una ricerca.",
        )
        auto_by_budget = st_mod.toggle(
            "Auto per budget (config)",
            value=bool(retriever_cfg.get("auto_by_budget", retriever_cfg.get("auto", False))),
            key="Auto per budget",
            help="Se attivo, riduce automaticamente i candidati in base al budget di latenza (config).",
        )

        st_mod.markdown("---")
        st_mod.markdown("### UI")
        skip_preflight = st_mod.toggle(
            "Salta preflight iniziale",
            value=bool(ui_cfg.get("skip_preflight", data.get("skip_preflight", False))),
            help="Persistente: memorizza ui.skip_preflight nel config del cliente.",
        )

        submitted = st_mod.form_submit_button("Salva modifiche", type="primary")

    return submitted, {
        "vision_engine": vision_engine,
        "vision_model": vision_model,
        "vision_strict": bool(vision_strict),
        "candidate_limit": int(candidate_limit),
        "latency_budget": int(latency_budget),
        "auto_by_budget": bool(auto_by_budget),
        "skip_preflight": bool(skip_preflight),
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
    throttle_cfg = _copy_section(new_retriever.get("throttle", {}))
    throttle_cfg["candidate_limit"] = int(values["candidate_limit"])
    latency_budget = int(values["latency_budget"])
    throttle_cfg["latency_budget_ms"] = latency_budget
    new_retriever["throttle"] = throttle_cfg
    auto_by_budget = bool(values["auto_by_budget"])
    new_retriever["auto_by_budget"] = auto_by_budget
    updates["retriever"] = new_retriever

    new_ui = _copy_section(ui_cfg)
    new_ui["skip_preflight"] = bool(values["skip_preflight"])
    updates["ui"] = new_ui

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


# ---------- helpers runtime / semantica ----------
def _render_runtime_retriever(slug: str, *, st_module: StreamlitLike | None = None) -> None:
    st_mod = st_module or get_streamlit()
    st_mod.markdown("### Retriever (runtime)")

    curr_limit, curr_budget_ms, curr_auto = get_retriever_settings(slug)

    new_limit = st_mod.number_input(
        "Candidate limit (runtime)",
        min_value=MIN_CANDIDATE_LIMIT,
        max_value=MAX_CANDIDATE_LIMIT,
        value=curr_limit,
        step=500,
        key="retr_limit_runtime",
        help="Numero massimo di candidati usati dal retriever per questo workspace (overlay runtime).",
    )
    new_budget_ms = st_mod.number_input(
        "Budget latenza (ms, runtime)",
        min_value=0,
        max_value=2000,
        value=curr_budget_ms,
        step=50,
        key="retr_budget_runtime",
        help="Tempo massimo di ricerca (ms) per questo workspace.",
    )
    new_auto = st_mod.toggle(
        "Auto per budget (runtime)",
        value=curr_auto,
        key="retr_auto_runtime",
        help="Se attivo, riduce automaticamente i candidati in base al budget di latenza runtime.",
    )

    if (int(new_limit), int(new_budget_ms), bool(new_auto)) != (
        int(curr_limit),
        int(curr_budget_ms),
        bool(curr_auto),
    ):
        set_retriever_settings(int(new_limit), int(new_budget_ms), bool(new_auto), slug=slug)
        try:
            st_mod.toast("Impostazioni retriever runtime salvate.")
        except Exception:
            pass


# ---------- entrypoint pagina ----------
def main() -> None:
    slug = render_chrome_then_require()
    layout = get_ui_workspace_layout(slug, require_env=False)
    ctx, settings = _load_context_and_settings(slug)
    data = settings.as_dict()

    st.subheader(f"Config & Settings – {slug}")
    st.info(
        "Questa pagina gestisce le impostazioni applicative del workspace. "
        "I segreti restano in .env e sono referenziati da chiavi *_env.",
        icon="ℹ️",
    )

    vision_cfg, retriever_cfg, ui_cfg = _extract_sections(data)
    assistant_env = vision_cfg.get("assistant_id_env") or "N/D"

    render_sidebar(slug, assistant_env, st_module=st)

    saved_flag = st.session_state.pop("config_editor_saved", False)
    if saved_flag:
        st.success("Configurazione aggiornata.")

    # Sezione: config YAML
    submitted, form_values = render_body(
        st_module=st,
        data=data,
        vision_cfg=vision_cfg,
        retriever_cfg=retriever_cfg,
        ui_cfg=ui_cfg,
        assistant_env=assistant_env,
    )

    st.markdown("---")
    _render_runtime_retriever(slug, st_module=st)

    # Danger zone - Cleanup
    cleanup_client_name = cleanup_component.client_display_name(slug, get_clients)
    cleanup_raw_folders = cleanup_component.list_raw_subfolders(slug, resolve_raw_dir, layout=layout)
    st.markdown("---")
    with st.expander("Danger zone · Cleanup cliente", expanded=False):
        st.markdown(f"**Cliente:** {cleanup_client_name}  \\\n**Google Drive:** `{slug}`")
        if cleanup_raw_folders:
            folders = ", ".join(f"`{name}`" for name in cleanup_raw_folders)
            st.markdown(f"**Cartelle RAW:** {folders}")
        else:
            st.markdown("**Cartelle RAW:** *(nessuna cartella trovata o RAW non presente)*")
        st.caption("Elimina workspace locale, registro clienti e (se configurato) la cartella Drive.")

        run_cleanup_fn = cleanup_component.resolve_run_cleanup()
        perform_cleanup_fn = cleanup_component.resolve_perform_cleanup()
        if run_cleanup_fn is None and perform_cleanup_fn is None:
            st.info(
                "Funzioni di cleanup non disponibili. Installa il modulo `tools.clean_client_workspace` "
                "per abilitare la cancellazione guidata."
            )
        if st.button(
            "Cancella cliente…",
            key="config_cleanup_open_confirm",
            type="secondary",
            help="Rimozione completa: locale, DB e Drive",
        ):
            cleanup_component.open_cleanup_modal(
                st=st,
                slug=slug,
                client_name=cleanup_client_name,
                set_slug=set_slug,
                run_cleanup=run_cleanup_fn,
                perform_cleanup=perform_cleanup_fn,
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
