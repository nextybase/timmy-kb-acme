# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/tools_check.py

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import read_text_safe
from ui.chrome import render_chrome_then_require
from ui.fine_tuning import open_system_prompt_modal, open_vision_modal, run_pdf_to_yaml_config
from ui.utils.stubs import get_streamlit

st = get_streamlit()
LOG = get_structured_logger("ui.tools_check")

_SS_VISION_OPEN = "ft_open_vision_modal"
_SS_SYS_OPEN = "ft_open_system_prompt"

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


def _is_gate_error(err: Exception) -> bool:
    """Compat per suite legacy: rileva il gate Vision dalle eccezioni."""
    message = str(err).casefold()
    if "vision" in message and "eseguit" in message:
        return True
    if "file=vision_hash" in message:
        return True
    marker = getattr(err, "file_path", None)
    if isinstance(marker, (str, Path)) and Path(marker).name == ".vision_hash":
        return True
    return False


def _st_rerun() -> None:
    rerun = getattr(st, "rerun", None)
    if callable(rerun):
        rerun()


def _trigger_modal(flag_key: str) -> None:
    st.session_state[flag_key] = True
    _st_rerun()


def _consume_flag(flag_key: str) -> bool:
    if flag_key in st.session_state and st.session_state[flag_key]:
        st.session_state[flag_key] = False
        return True
    return False


def _render_controls(slug: str) -> None:
    col_vision, col_pdf, col_sys = st.columns([1, 1, 1])
    with col_vision:
        if st.button("Apri Vision Statement", type="primary", key="btn_open_vision_modal"):
            st.session_state[_SS_SYS_OPEN] = False
            _trigger_modal(_SS_VISION_OPEN)

    with col_pdf:
        if st.button(
            "PDF -> YAML (config/)",
            key="btn_pdf_to_yaml",
            help="Converte config/VisionStatement.pdf in config/vision_statement.yaml",
        ):
            try:
                run_pdf_to_yaml_config()
            except Exception as exc:  # pragma: no cover
                LOG.warning("ui.tools_check.pdf_to_yaml_error", extra={"err": str(exc)})
                st.error(f"Errore durante la conversione: {exc}")

    with col_sys:
        if st.button("Apri System Prompt", key="btn_open_system_prompt"):
            st.session_state[_SS_VISION_OPEN] = False
            _trigger_modal(_SS_SYS_OPEN)

    if _consume_flag(_SS_VISION_OPEN):
        open_vision_modal(slug=slug)
    elif _consume_flag(_SS_SYS_OPEN):
        open_system_prompt_modal()

    last_result = st.session_state.get("ft_last_vision_result")
    if last_result:
        with st.expander("Ultimo output Vision", expanded=False):
            mapping_data = None
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
                areas = mapping_data.get("areas") or []
                st.markdown("### Aree generate")
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

                        st.markdown(f"**Ambito:** `{ambito}`  \n" f"**Descrizione breve:** {breve}")

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
                                st.markdown(
                                    "\n".join(f"- `{ent.get('id')}` ({ent.get('label', '-')})" for ent in entities)
                                )
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
                        st.json(metadata_policy)

                with st.expander("JSON completo", expanded=False):
                    st.json(mapping_data)
            elif last_result:
                with st.expander("JSON completo", expanded=False):
                    st.json(last_result)


def _render_advanced_options() -> None:
    with st.expander("Opzioni avanzate"):
        if st.button("Azzera stato pagina", key="btn_reset_state", type="secondary"):
            keys_to_clear = [k for k in st.session_state if str(k).startswith(("ft_", "_SS_"))]
            for key in keys_to_clear:
                st.session_state.pop(key, None)
            st.success("Stato ripulito.")


def main() -> None:
    render_chrome_then_require(allow_without_slug=True)
    slug: Optional[str] = st.session_state.get("active_slug") or "dummy"

    st.header("Tools > Tuning")
    st.caption("Interfaccia rapida per modali Vision/System Prompt e conversione PDF -> YAML.")

    _render_controls(slug=slug or "dummy")
    _render_advanced_options()


if __name__ == "__main__":
    main()
