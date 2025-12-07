# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple, cast

from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.import_utils import import_from_candidates
from pipeline.logging_utils import get_structured_logger
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


def _get_client() -> Any:
    """Restituisce un client OpenAI preferendo la factory del progetto."""
    factory_candidates = [
        "ai.client_factory:make_openai_client",
        "..ai.client_factory:make_openai_client",
    ]
    try:
        factory = import_from_candidates(
            factory_candidates,
            package=__package__,
            description="make_openai_client",
            logger=LOG,
        )
        return factory()
    except ImportError:
        try:
            openai_ctor = import_from_candidates(
                ["openai:OpenAI"],
                description="OpenAI",
                logger=LOG,
            )
            return openai_ctor()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Impossibile inizializzare il client OpenAI: {exc}") from exc


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


def _resolve_ui_assistant_id() -> str:
    """Risoluzione assistant_id: OBNEXT_ASSISTANT_ID -> ASSISTANT_ID -> errore."""
    asst_id = get_env_var("OBNEXT_ASSISTANT_ID", default=None) or get_env_var("ASSISTANT_ID", default=None)
    if not asst_id:
        raise ConfigError("Assistant ID mancante (env: OBNEXT_ASSISTANT_ID o ASSISTANT_ID).")
    return asst_id


def _retrieve_assistant(client: Any, assistant_id: str) -> Any:
    """Wrapper centralizzato per retrieve dell'assistant."""
    if hasattr(client, "assistants"):
        assistants = getattr(client, "assistants")
        if hasattr(assistants, "retrieve"):
            return assistants.retrieve(assistant_id)
    # fallback deprecato incapsulato
    beta = getattr(client, "beta", None)
    if beta is None or not hasattr(beta, "assistants"):
        raise ConfigError("Client OpenAI non espone l'API assistants.")
    return beta.assistants.retrieve(assistant_id)


def _update_assistant(client: Any, assistant_id: str, instructions: str) -> Any:
    """Wrapper centralizzato per update dell'assistant."""
    if hasattr(client, "assistants"):
        assistants = getattr(client, "assistants")
        if hasattr(assistants, "update"):
            return assistants.update(assistant_id, instructions=instructions)
    beta = getattr(client, "beta", None)
    if beta is None or not hasattr(beta, "assistants"):
        raise ConfigError("Client OpenAI non espone l'API assistants.")
    return beta.assistants.update(assistant_id, instructions=instructions)


def load_remote_system_prompt(assistant_id: str, client: Any) -> Dict[str, str]:
    """Carica modello e prompt remoto in modo incapsulato."""
    try:
        assistant = _retrieve_assistant(client, assistant_id)
        model = getattr(assistant, "model", "") or ""
        instructions = getattr(assistant, "instructions", "") or ""
        return {"model": model, "instructions": instructions}
    except Exception as exc:
        LOG.warning(
            "ui.system_prompt.assistant_retrieve_failed",
            extra={"assistant_id": assistant_id, "error": str(exc)},
        )
        raise ConfigError(f"Errore nel recupero dell'assistant {assistant_id}: {exc}") from exc


def save_remote_system_prompt(assistant_id: str, instructions: str, client: Any) -> None:
    """Salva il prompt remoto incapsulando l'accesso API."""
    try:
        _update_assistant(client, assistant_id, instructions=instructions)
    except Exception as exc:
        LOG.warning(
            "ui.system_prompt.assistant_update_failed",
            extra={"assistant_id": assistant_id, "error": str(exc)},
        )
        raise ConfigError(f"Errore durante il salvataggio del prompt su {assistant_id}: {exc}") from exc


def open_system_prompt_modal() -> None:
    dialog_factory = getattr(st, "dialog", None)
    if not callable(dialog_factory):
        st.error("La versione corrente di Streamlit non supporta i dialog.")
        return

    DialogFactory = Callable[[str], Callable[[Callable[[], None]], Callable[[], None]]]
    dialog = cast(DialogFactory, dialog_factory)

    @dialog("System Prompt - Assistente")
    def _inner() -> None:
        apply_modal_css()
        try:
            asst_id = _resolve_ui_assistant_id()
            client = _get_client()
            assistant_payload = load_remote_system_prompt(asst_id, client)
            model = assistant_payload.get("model", "")
            sys_text = assistant_payload.get("instructions", "") or ""
        except Exception as exc:
            LOG.warning("ui.system_prompt.error", extra={"err": str(exc)})
            st.error("Impossibile caricare il system prompt dell'assistente. Verifica la configurazione.")
            if st.button("Chiudi", key="ft_sys_prompt_close_error"):
                st.session_state.pop(_SS_TEXT, None)
                st.session_state.pop(_SS_SECTIONS, None)
                _st_rerun()
            return

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
                try:
                    save_remote_system_prompt(asst_id, full_prompt, client)
                    st.session_state[_SS_SECTIONS] = _split_system_prompt(full_prompt)
                    st.success("System prompt aggiornato.")
                except Exception as exc:
                    LOG.warning("ui.system_prompt.update_error", extra={"err": str(exc)})
                    st.error(f"Errore durante il salvataggio: {exc}")

            if col_close.button("Chiudi", key="ft_sys_prompt_close"):
                st.session_state.pop(_SS_TEXT, None)
                st.session_state.pop(_SS_SECTIONS, None)
                _st_rerun()
        except Exception as exc:
            LOG.warning("ui.system_prompt.error", extra={"err": str(exc)})
            st.error("Errore inatteso durante il rendering del system prompt.")

    _inner()
