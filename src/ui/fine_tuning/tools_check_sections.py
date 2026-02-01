# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/fine_tuning/tools_check_sections.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pipeline import ontology
from pipeline.path_utils import read_text_safe
from ui.utils.control_plane import display_control_plane_result, run_control_plane_tool
from ui.utils.stubs import get_streamlit

from .system_prompt_modal import open_system_prompt_modal
from .vision_modal import open_vision_modal

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


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


def render_controls(slug: str, *, st_module: Any | None = None) -> None:
    """Renderizza i controlli principali della pagina tools_check."""
    st = st_module or get_streamlit()

    col_vision, col_pdf, col_sys = st.columns([1, 1, 1])
    with col_vision:
        if st.button("Apri Vision Statement", type="primary", key="btn_open_vision_modal"):
            st.session_state[SS_SYS_OPEN] = False
            _trigger_modal(st, SS_VISION_OPEN)

    with col_pdf:
        if st.button(
            "PDF -> YAML (workspace)",
            key="btn_pdf_to_yaml",
            help="Converte VisionStatement.pdf in output/<workspace>/config/visionstatement.yaml",
        ):
            payload = run_control_plane_tool(
                tool_module="tools.tuning_pdf_to_yaml",
                slug=slug,
                action="pdf_to_yaml",
            )["payload"]
            display_control_plane_result(
                st,
                payload,
                success_message="VisionStatement.yaml aggiornato nel workspace.",
            )
            if payload.get("status") == "ok":
                paths = payload.get("paths") or {}
                yaml_path = paths.get("vision_yaml")
                if yaml_path:
                    try:
                        preview = read_text_safe(Path(yaml_path).parent, Path(yaml_path))
                        st.code(preview, language="yaml")
                    except Exception:
                        st.warning("Impossibile mostrare l'anteprima YAML.")

    with col_sys:
        if st.button("Apri System Prompt", key="btn_open_system_prompt"):
            st.session_state[SS_VISION_OPEN] = False
            _trigger_modal(st, SS_SYS_OPEN)

    # Preview README/entità se disponibile un mapping in sessione
    last_result = st.session_state.get(STATE_LAST_VISION_RESULT)
    mapping_data = _load_mapping_data(last_result)
    if mapping_data:
        try:
            render_readme_preview(mapping_data, ontology.get_all_entities(), st_module=st)
        except Exception:
            pass

    if _consume_flag(st, SS_VISION_OPEN):
        open_vision_modal(slug=slug)
    elif _consume_flag(st, SS_SYS_OPEN):
        open_system_prompt_modal()

    if last_result:
        render_vision_output(last_result, st_module=st)


def render_vision_output(last_result: Any, *, st_module: Any | None = None) -> None:
    """Mostra i risultati dell'ultima Vision eseguita (mapping YAML, metadata, areas)."""
    st = st_module or get_streamlit()
    with st.expander("Ultimo output Vision", expanded=False):
        mapping_data = _load_mapping_data(last_result)

        if isinstance(mapping_data, dict) and mapping_data.get("areas"):
            _render_mapping_areas(mapping_data, st)
            _render_entities_section(mapping_data, st)
            _render_diagnostics(mapping_data, st)
        elif last_result:
            _emit_json(st, last_result)


def _load_mapping_data(last_result: Any) -> Optional[Dict[str, Any]]:
    mapping_data: Optional[Dict[str, Any]] = None
    if isinstance(last_result, dict):
        mapping_path = last_result.get("mapping")
        if isinstance(mapping_path, str) and yaml is not None:
            try:
                mapping_file = Path(mapping_path)
                text = read_text_safe(mapping_file.parent, mapping_file)
                mapping_data = yaml.safe_load(text) or {}
            except Exception:
                mapping_data = None
    return mapping_data


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

    _render_diagnostics(mapping_data, st)
    with st.expander("JSON completo", expanded=False):
        _emit_json(st, mapping_data)


def _emit_json(st_module: Any, payload: Any) -> None:
    json_renderer = getattr(st_module, "json", None)
    if callable(json_renderer):
        json_renderer(payload)
    else:  # pragma: no cover - degradazione per test/headless
        st_module.markdown(f"```json\n{payload}\n```")


def _global_vocab() -> Dict[str, Dict[str, Any]]:
    """Indicizza le entità globali per id/label (lowercase)."""
    vocab: Dict[str, Dict[str, Any]] = {}
    try:
        for ent in ontology.get_all_entities():
            ent_id = str(ent.get("id") or "").strip()
            label = str(ent.get("label") or "").strip()
            if ent_id:
                vocab.setdefault(ent_id.lower(), ent)
            if label:
                vocab.setdefault(label.lower(), ent)
    except Exception:
        return {}
    return vocab


def _render_entities_section(mapping_data: Dict[str, Any], st: Any) -> None:
    entities = mapping_data.get("entities") or []
    vocab = _global_vocab()

    if entities:
        st.markdown("### Entità rilevanti (da l'assistant)")
        rows: List[str] = ["| Entità | Categoria |", "| --- | --- |"]
        out_of_vocab = False
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "").strip()
            category = str(ent.get("category") or "").strip()
            rows.append(f"| {name} | {category} |")
            if name and name.lower() not in vocab:
                out_of_vocab = True
        st.markdown("\n".join(rows))
        if out_of_vocab:
            st.warning("ATTENZIONE: entità fuori dal vocabolario NeXT")


def _render_diagnostics(mapping_data: Dict[str, Any], st: Any) -> None:
    st.markdown("### Diagnostica VisionOutput")
    entities = mapping_data.get("entities") or []
    er_model = mapping_data.get("er_model") or {}
    vocab = _global_vocab()

    names = [str(e.get("name") or "").strip() for e in entities if isinstance(e, dict)]
    dup = sorted({n for n in names if n and names.count(n) > 1})
    if dup:
        st.error(f"Entità duplicate: {', '.join(dup)}")
    else:
        st.success("Entità duplicate: PASS")

    out_of_vocab = [n for n in names if n and n.lower() not in vocab]
    if out_of_vocab:
        st.warning(f"Entità non riconosciute: {', '.join(out_of_vocab)}")
    else:
        st.success("Entità non riconosciute: PASS")

    if not isinstance(er_model, dict) or not er_model:
        st.warning("ER model mancante o incompleto")
    else:
        er_entities = er_model.get("entities") or []
        er_rel = er_model.get("relations") or []
        if not er_entities or not er_rel:
            st.warning("ER model incompleto (entities/relations)")
        else:
            st.success("ER model completo")


def render_readme_preview(
    mapping_data: Dict[str, Any],
    global_entities: List[Dict[str, Any]],
    *,
    st_module: Any | None = None,
) -> None:
    """Mostra una preview del README basata su mapping + vocabolario globale."""
    st = st_module or get_streamlit()
    with st.expander("Preview README", expanded=False):
        entities = mapping_data.get("entities") or []

        idx: Dict[str, Dict[str, Any]] = {}
        for ent in global_entities or []:
            ent_id = str(ent.get("id") or "").strip().lower()
            label = str(ent.get("label") or "").strip().lower()
            if ent_id:
                idx.setdefault(ent_id, ent)
            if label:
                idx.setdefault(label, ent)

        st.markdown("#### Entità rilevanti")
        rows = ["| Entità | Categoria | Esempi |", "| --- | --- | --- |"]
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "").strip()
            meta = idx.get(name.lower())
            category = ent.get("category") or (meta or {}).get("category", "")
            examples = ", ".join((meta or {}).get("examples") or [])
            rows.append(f"| {name} | {category} | {examples} |")
        st.markdown("\n".join(rows))

        areas = mapping_data.get("areas") or []
        if areas:
            st.markdown("#### Sezioni previste nel README")
            st.markdown("\n".join(f"- Area `{a.get('key')}`: {a.get('descrizione_breve', '')}" for a in areas))


def render_global_entities(*, st_module: Any | None = None) -> None:
    """Visualizza le entità globali caricate da ontology.yaml, organizzate per categoria."""
    st = st_module or get_streamlit()
    with st.expander("Entità globali di NeXT", expanded=False):
        try:
            data = ontology.load_entities()
        except Exception as exc:  # pragma: no cover - degradazione UI
            st.warning(f"Impossibile caricare le entità globali: {exc}")
            return

        categories = data.get("categories") if isinstance(data, dict) else {}
        if not isinstance(categories, dict) or not categories:
            st.info("Nessuna entità globale disponibile.")
            return

        for cat_id, meta in categories.items():
            if not isinstance(meta, dict):
                continue
            label = meta.get("label") or cat_id
            entities = meta.get("entities") or []
            with st.expander(str(label), expanded=False):
                for ent in entities:
                    if not isinstance(ent, dict):
                        continue
                    ent_id = ent.get("id") or "-"
                    name = ent.get("label") or ent_id
                    code = ent.get("document_code") or "-"
                    examples = ent.get("examples") or []
                    st.markdown(f"- **{name}** (`{ent_id}`) - codice: `{code}`")
                    if examples:
                        st.markdown("  - Esempi: " + ", ".join(str(x) for x in examples))


def render_advanced_options(*, st_module: Any | None = None) -> None:
    """Renderizza le opzioni avanzate (reset state)."""
    st = st_module or get_streamlit()
    with st.expander("Opzioni avanzate"):
        if st.button("Azzera stato pagina", key="btn_reset_state", type="secondary"):
            keys_to_clear = [k for k in list(st.session_state) if str(k).startswith(tuple(_RESET_PREFIXES))]
            for key in keys_to_clear:
                st.session_state.pop(key, None)
            st.success("Stato ripulito.")
        render_global_entities(st_module=st)
