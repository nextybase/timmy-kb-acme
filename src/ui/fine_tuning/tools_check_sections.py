# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/fine_tuning/tools_check_sections.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import read_text_safe
from ui.utils.stubs import get_streamlit

from .pdf_tools import run_pdf_to_yaml_config
from .system_prompt_modal import open_system_prompt_modal
from .vision_modal import open_vision_modal

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

LOG = get_structured_logger("ui.tools_check")

SS_VISION_OPEN = "ft_open_vision_modal"
SS_SYS_OPEN = "ft_open_system_prompt"
STATE_LAST_VISION_RESULT = "ft_last_vision_result"
_RESET_PREFIXES: Iterable[str] = ("ft_", "_SS_")

__all__ = [
    "render_controls",
    "render_vision_output",
    "render_advanced_options",
    "SS_VISION_OPEN",
    "SS_SYS_OPEN",
    "STATE_LAST_VISION_RESULT",
]


def _st_rerun(st_module: Any) -> None:
    rerun = getattr(st_module, "rerun", None)
    if callable(rerun):
        rerun()


def _trigger_modal(st_module: Any, flag_key: str) -> None:
    st_module.session_state[flag_key] = True
    _st_rerun(st_module)


def _consume_flag(st_module: Any, flag_key: str) -> bool:
    if st_module.session_state.get(flag_key):
        st_module.session_state[flag_key] = False
        return True
    return False


def render_controls(
    slug: str,
    *,
    st_module: Any | None = None,
    logger: Any | None = None,
) -> None:
    """Renderizza i controlli principali della pagina tools_check."""
    st = st_module or get_streamlit()
    log = logger or LOG

    col_vision, col_pdf, col_sys = st.columns([1, 1, 1])
    with col_vision:
        if st.button("Apri Vision Statement", type="primary", key="btn_open_vision_modal"):
            st.session_state[SS_SYS_OPEN] = False
            _trigger_modal(st, SS_VISION_OPEN)

    with col_pdf:
        if st.button(
            "PDF -> YAML (config/)",
            key="btn_pdf_to_yaml",
            help="Converte config/VisionStatement.pdf in config/vision_statement.yaml",
        ):
            try:
                run_pdf_to_yaml_config()
            except Exception as exc:  # pragma: no cover
                if log:
                    log.warning("ui.tools_check.pdf_to_yaml_error", extra={"err": str(exc)})
                st.error(f"Errore durante la conversione: {exc}")

    with col_sys:
        if st.button("Apri System Prompt", key="btn_open_system_prompt"):
            st.session_state[SS_VISION_OPEN] = False
            _trigger_modal(st, SS_SYS_OPEN)

    if _consume_flag(st, SS_VISION_OPEN):
        open_vision_modal(slug=slug)
    elif _consume_flag(st, SS_SYS_OPEN):
        open_system_prompt_modal()

    last_result = st.session_state.get(STATE_LAST_VISION_RESULT)
    if last_result:
        render_vision_output(last_result, st_module=st)


def render_vision_output(last_result: Any, *, st_module: Any | None = None) -> None:
    """Mostra i risultati dell'ultima Vision eseguita (mapping YAML, metadata, areas)."""
    st = st_module or get_streamlit()
    with st.expander("Ultimo output Vision", expanded=False):
        mapping_data: Optional[Dict[str, Any]] = None
        if isinstance(last_result, dict):
            mapping_path = last_result.get("mapping")
            if isinstance(mapping_path, str) and yaml is not None:
                try:
                    mapping_file = Path(mapping_path)
                    text = read_text_safe(mapping_file.parent, mapping_file)
                    mapping_data = yaml.safe_load(text) or {}
                except Exception as exc:
                    st.warning(f"Impossibile leggere semantic_mapping.yaml: {exc}")

        if isinstance(mapping_data, dict) and mapping_data.get("areas"):
            _render_mapping_areas(mapping_data, st)
        elif last_result:
            _emit_json(st, last_result)


def _render_mapping_areas(mapping_data: Dict[str, Any], st: Any) -> None:
    st.markdown("### Aree generate")
    areas = mapping_data.get("areas") or []
    for idx, area in enumerate(areas, start=1):
        title = f"{idx}. {area.get('key', 'area')}"
        with st.expander(title, expanded=False):
            ambito = area.get("ambito", "")
            breve = area.get("descrizione_breve", "")
            dettagli = area.get("descrizione_dettagliata", {}) or {}
            include = dettagli.get("include") or []
            exclude = dettagli.get("exclude") or []
            artefatti_note = dettagli.get("artefatti_note")
            documents = area.get("documents") or []
            artefatti = area.get("artefatti") or []
            correlazioni = area.get("correlazioni") or {}

            st.markdown(f"**Ambito:** `{ambito}`  \n**Descrizione breve:** {breve}")

            if include:
                st.markdown("**Include:**")
                st.markdown("\n".join(f"- {item}" for item in include))
            if exclude:
                st.markdown("**Exclude:**")
                st.markdown("\n".join(f"- {item}" for item in exclude))
            if artefatti_note:
                st.markdown(f"**Note artefatti:** {artefatti_note}")

            if documents:
                st.markdown("**Documents:**")
                st.markdown("\n".join(f"- {doc}" for doc in documents))

            if artefatti:
                st.markdown("**Artefatti:**")
                st.markdown("\n".join(f"- {art}" for art in artefatti))

            entities = correlazioni.get("entities") or []
            relations = correlazioni.get("relations") or []
            hints = correlazioni.get("chunking_hints") or []
            if entities or relations or hints:
                st.markdown("**Correlazioni:**")
                if entities:
                    st.markdown("*Entities*")
                    st.markdown("\n".join(f"- `{ent.get('id')}` ({ent.get('label', '-')})" for ent in entities))
                if relations:
                    st.markdown("*Relations*")
                    relation_lines: List[str] = []
                    for rel in relations:
                        subj = rel.get("subj")
                        pred = rel.get("pred")
                        obj = rel.get("obj")
                        card = rel.get("card")
                        relation_lines.append(f"- {subj} --{pred}--> {obj} ({card})")
                    st.markdown("\n".join(relation_lines))
                if hints:
                    st.markdown("*Chunking hints*")
                    st.markdown("\n".join(f"- {hint}" for hint in hints))

    metadata_policy = mapping_data.get("metadata_policy")
    if metadata_policy:
        with st.expander("Metadata policy", expanded=False):
            _emit_json(st, metadata_policy)

    with st.expander("JSON completo", expanded=False):
        _emit_json(st, mapping_data)


def _emit_json(st_module: Any, payload: Any) -> None:
    json_renderer = getattr(st_module, "json", None)
    if callable(json_renderer):
        json_renderer(payload)
    else:  # pragma: no cover - fallback per test/headless
        st_module.markdown(f"```json\n{payload}\n```")


def render_advanced_options(*, st_module: Any | None = None) -> None:
    """Renderizza le opzioni avanzate (reset state)."""
    st = st_module or get_streamlit()
    with st.expander("Opzioni avanzate"):
        if st.button("Azzera stato pagina", key="btn_reset_state", type="secondary"):
            keys_to_clear = [k for k in list(st.session_state) if str(k).startswith(tuple(_RESET_PREFIXES))]
            for key in keys_to_clear:
                st.session_state.pop(key, None)
            st.success("Stato ripulito.")
