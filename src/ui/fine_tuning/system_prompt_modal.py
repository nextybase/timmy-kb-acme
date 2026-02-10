# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Callable, Dict, List, Tuple, cast

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.system_prompt_api import build_openai_client, load_remote_system_prompt, resolve_assistant_id
from ui.utils.control_plane import display_control_plane_result, run_control_plane_tool
from ui.utils.stubs import get_streamlit

from .styles import apply_modal_css

st = get_streamlit()

LOG = get_structured_logger("ui.system_prompt_modal")
_SS_TEXT = "ft_sys_prompt_text"
_SS_SECTIONS = "ft_sys_prompt_sections"
_HEADING_ORDER: Tuple[str, ...] = (
    "TUO RUOLO",
    "INPUT",
    "CONOSCENZE E FONTI",
    "LESSICO OBBLIGATORIO",
    "CONTRATTO DI OUTPUT (STRICT)",
    "PROCESSO (PASSI MENTALI)",
    "GATE HALT (INSUFFICIENTE)",
    "POLITICHE DI DETERMINISMO",
    "SCHEMA DI OUTPUT (SCHELETRO GUIDA)",
    "STILE DI USCITA",
)


def _st_rerun() -> None:
    rerun = getattr(st, "rerun", None)
    if callable(rerun):  # pragma: no cover - dipende dal runtime
        rerun()


def _split_system_prompt(text: str) -> Dict[str, str]:
    """Divide il prompt in sezioni fisse basate sugli heading richiamati dalla KB."""
    buckets: Dict[str, List[str]] = {heading: [] for heading in _HEADING_ORDER}
    if not text:
        return {heading: "" for heading in _HEADING_ORDER}

    current = _HEADING_ORDER[0]
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        upper_line = stripped.upper()
        if upper_line in buckets:
            current = upper_line
            continue
        buckets[current].append(raw_line.rstrip())

    return {heading: "\n".join(lines).strip() for heading, lines in buckets.items()}


def _join_sections(sections: Dict[str, str]) -> str:
    """Ricostruisce il prompt completo usando la sequenza di heading canonica."""
    parts: List[str] = []
    for heading in _HEADING_ORDER:
        content = sections.get(heading, "").strip()
        section = f"{heading}\n"
        if content:
            section += f"{content}\n"
        parts.append(section.strip())
    return "\n\n".join(part for part in parts if part).strip()


def open_system_prompt_modal(*, slug: str = "dummy") -> None:
    dialog_factory = getattr(st, "dialog", None)
    if not callable(dialog_factory):
        # Strict UI: capability mancante => STOP (non degradare a "mezzo successo").
        LOG.error("ui.system_prompt.dialog_unavailable", extra={"slug": slug or "", "decision": "STOP"})
        st.error("Streamlit non supporta i dialog: operazione non eseguibile in modalità strict.")
        stop_fn = getattr(st, "stop", None)
        if callable(stop_fn):
            stop_fn()
        raise ConfigError("Streamlit dialog non disponibile per System Prompt modal.", slug=slug or "")

    DialogFactory = Callable[[str], Callable[[Callable[[], None]], Callable[[], None]]]
    dialog = cast(DialogFactory, dialog_factory)

    @dialog("System Prompt - Assistente")
    def _inner() -> None:
        apply_modal_css()
        try:
            asst_id = resolve_assistant_id()
            client = build_openai_client()
            assistant_payload = load_remote_system_prompt(asst_id, client)
            model = assistant_payload.get("model", "")
            sys_text = assistant_payload.get("instructions", "") or ""
        except Exception as exc:
            LOG.error("ui.system_prompt.load_failed", extra={"slug": slug or "", "err": str(exc), "decision": "STOP"})
            st.error("Impossibile caricare il system prompt dell'assistente. Verifica la configurazione.")
            if st.button("Chiudi", key="ft_sys_prompt_close_error"):
                st.session_state.pop(_SS_TEXT, None)
                st.session_state.pop(_SS_SECTIONS, None)
                _st_rerun()
            stop_fn = getattr(st, "stop", None)
            if callable(stop_fn):
                stop_fn()

        try:
            st.caption(f"assistant_id: {asst_id}" + (f" - model: {model}" if model else ""))

            if _SS_SECTIONS not in st.session_state or _SS_TEXT not in st.session_state:
                sections_init = _split_system_prompt(sys_text)
                st.session_state[_SS_SECTIONS] = sections_init
                st.session_state[_SS_TEXT] = _join_sections(sections_init)

            sections = cast(Dict[str, str], st.session_state.get(_SS_SECTIONS, {}))

            updated_sections: Dict[str, str] = {}
            for heading in _HEADING_ORDER:
                with st.expander(heading, expanded=False):
                    value = sections.get(heading, "")
                    updated_sections[heading] = st.text_area(
                        f"{heading}_body",
                        value=value,
                        height=180,
                        key=f"{_SS_SECTIONS}_{heading}",
                    )

            st.session_state[_SS_SECTIONS] = updated_sections
            full_prompt = _join_sections(updated_sections)
            st.session_state[_SS_TEXT] = full_prompt

            with st.expander("Prompt completo (readonly)", expanded=False):
                st.code(full_prompt or "<vuoto>", language="markdown")

            col_save, col_close = st.columns([1, 1])

            if col_save.button("Salva", key="ft_sys_prompt_save", type="primary"):
                payload = run_control_plane_tool(
                    tool_module="tools.tuning_system_prompt",
                    slug=slug,
                    action="system_prompt.set",
                    args=["--mode", "set", "--instructions", full_prompt],
                )["payload"]
                display_control_plane_result(st, payload, success_message="System prompt aggiornato sul remote.")
                if payload.get("status") == "ok":
                    stored = payload.get("instructions") or full_prompt
                    st.session_state[_SS_SECTIONS] = _split_system_prompt(stored)
                    st.session_state[_SS_TEXT] = stored

            if col_close.button("Chiudi", key="ft_sys_prompt_close"):
                st.session_state.pop(_SS_TEXT, None)
                st.session_state.pop(_SS_SECTIONS, None)
                _st_rerun()
        except Exception as exc:
            LOG.error("ui.system_prompt.render_failed", extra={"slug": slug or "", "err": str(exc), "decision": "STOP"})
            st.error("Errore inatteso durante il rendering del system prompt.")
            stop_fn = getattr(st, "stop", None)
            if callable(stop_fn):
                stop_fn()
            raise ConfigError("Render system prompt fallito.", slug=slug or "") from exc

    _inner()
