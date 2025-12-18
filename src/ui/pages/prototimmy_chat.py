# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/prototimmy_chat.py
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence, cast

from ai.assistant_registry import resolve_ocp_executor_config, resolve_prototimmy_config
from ai.check import run_prototimmy_dummy_check
from ai.codex_runner import run_codex_cli
from ai.responses import run_json_model, run_text_model
from ai.types import AssistantConfig
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings
from rosetta import get_rosetta_client
from ui.chrome import render_chrome_then_require
from ui.utils.repo_root import get_repo_root
from ui.utils.stubs import get_streamlit

st = get_streamlit()

_SESSION_KEY = "prototimmy_messages"
_SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "Sei ProtoTimmy, assistente di pianificazione tecnica e coordinamento. "
        "Rispondi in modo conciso, operativo e orientato al contesto del workspace."
    ),
}

_PROTO_JSON_SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "Sei ProtoTimmy, assistente di pianificazione tecnica e coordinamento. "
        "Rispondi SOLO in JSON con le chiavi reply_to_user e message_for_ocp. "
        "Se il flusso richiede un intervento di OCP (keyword: OCP, ocp_executor, inoltra a OCP), "
        "valorizza message_for_ocp con la richiesta secca; altrimenti mantienilo vuoto."
    ),
}

_PROTO_JSON_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ProtoTimmyOCPOuput",
        "schema": {
            "type": "object",
            "properties": {
                "reply_to_user": {"type": "string"},
                "message_for_ocp": {"type": "string"},
            },
            "required": ["reply_to_user", "message_for_ocp"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_OCP_SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "Sei OCP_executor. Rispondi in modo tecnico, conciso e operativo. "
        "Non simulare azioni e non generare testo narrativo."
    ),
}

_CODEX_VALIDATION_SYSTEM = {
    "role": "system",
    "content": (
        "Sei OCP_executor. Valida l'output manuale di Codex CLI in formato JSON. "
        "Rispondi SOLO con le chiavi ok, issues, next_prompt_for_codex e stop_code. "
        "stop_code = 'HITL_REQUIRED' se è necessaria la supervisione umana."
    ),
}

_CODEX_VALIDATION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "CodexManualValidation",
        "schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "next_prompt_for_codex": {"type": "string"},
                "stop_code": {"type": "string"},
            },
            "required": ["ok", "issues", "next_prompt_for_codex", "stop_code"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_TRANSCRIPT_MAX_LINES = 20
_CODEX_PROMPT_KEY = "codex_turn_prompt"
_CODEX_OUTPUT_KEY = "codex_manual_output"
_CODEX_HITL_KEY = "codex_hitl_required"
_CODEX_HITL_CODE = "HITL_REQUIRED"
_CODEX_CLI_CMD: list[str] = ["codex", "run"]
_CODEX_CLI_TIMEOUT_S = 60

ROSETTA_HOOK_LOGGER = get_structured_logger("prototimmy.rosetta_hook")


def _build_chat_invocation(
    cfg: AssistantConfig,
    *,
    component: str,
    operation: str,
    step: str | None = None,
    request_tag: str | None = None,
) -> dict[str, Any]:
    invocation: dict[str, Any] = {
        "component": component,
        "operation": operation,
        "assistant_id": cfg.assistant_id,
        "strict_output": cfg.strict_output,
        "use_kb": cfg.use_kb,
    }
    if step:
        invocation["step"] = step
    if request_tag:
        invocation["request_tag"] = request_tag
    return invocation


def _load_settings() -> Settings:
    return Settings.load(get_repo_root())


def _ensure_history() -> list[dict[str, str]]:
    history = cast(list[dict[str, str]], st.session_state.setdefault(_SESSION_KEY, []))
    if not history or history[0].get("role") != "system":
        history.insert(0, dict(_SYSTEM_MESSAGE))
    return history


def _render_history(history: Iterable[Mapping[str, str]]) -> None:
    chat_message = getattr(st, "chat_message", None)
    for message in history:
        role = (message.get("role") or "user").strip().lower()
        content = (message.get("content") or "").strip()
        if not content:
            continue
        if callable(chat_message):
            with st.chat_message(role):
                st.write(content)
        else:
            st.markdown(f"**{role.title()}**: {content}")


def _collect_user_input() -> str | None:
    candidate = None
    if callable(getattr(st, "chat_input", None)):
        text = st.chat_input("Scrivi un messaggio a ProtoTimmy")
        if text:
            candidate = text.strip()
    else:
        text = st.text_area("Messaggio", key="prototimmy_chat_input")
        if st.button("Invia messaggio"):
            if text:
                candidate = text.strip()
            st.session_state["prototimmy_chat_input"] = ""
    if candidate:
        candidate = candidate.strip()
    return candidate or None


def _build_transcript(history: Sequence[Mapping[str, str]]) -> str:
    lines: list[str] = []
    filtered = [(msg.get("role") or "", msg.get("content") or "") for msg in history if isinstance(msg, Mapping)]
    for role_raw, content_raw in filtered[-_TRANSCRIPT_MAX_LINES:]:
        role = str(role_raw).strip().lower()
        content = str(content_raw).strip()
        if not content:
            continue
        if role not in {"user", "assistant"}:
            continue
        label = "UTENTE" if role == "user" else "PROTOTIMMY"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def _call_ocp(message: str) -> str:
    settings = _load_settings()
    cfg = resolve_ocp_executor_config(settings)
    response = run_text_model(
        model=cfg.model,
        messages=(
            dict(_OCP_SYSTEM_MESSAGE),
            {"role": "user", "content": f"Rispondi con i dati richiesti: {message}"},
        ),
        invocation=_build_chat_invocation(
            cfg,
            component="prototimmy.chat",
            operation="prototimmy.chat.ocp",
            step="ocp",
            request_tag="prototimmy_chat_ocp",
        ),
    )
    return cast(str, response.text)


def _render_ocp_response(text: str) -> None:
    with st.expander("Risposta OCP", expanded=False):
        st.write(text)


def _get_codex_prompt() -> str:
    prompt = st.session_state.setdefault(
        _CODEX_PROMPT_KEY,
        "Prompt fornito da OCP per la prossima esecuzione Codex CLI.",
    )
    return cast(str, prompt)


def _validate_codex_output(output: str) -> None:
    if not output.strip():
        st.error("Output Codex vuoto; incollare l'output CLI e riprovare.")
        return
    try:
        settings = _load_settings()
        cfg = resolve_ocp_executor_config(settings)
        response = run_json_model(
            model=cfg.model,
            messages=(
                dict(_CODEX_VALIDATION_SYSTEM),
                {"role": "user", "content": output},
            ),
            response_format=_CODEX_VALIDATION_RESPONSE_FORMAT,
            invocation=_build_chat_invocation(
                cfg,
                component="prototimmy.chat",
                operation="prototimmy.chat.codex_validation",
                request_tag="prototimmy_chat_codex_validation",
            ),
        )
        data = cast(dict[str, Any], response.data)
        st.json(data)
        ok = bool(data.get("ok"))
        issues = [str(item) for item in data.get("issues") or []]
        next_prompt = str(data.get("next_prompt_for_codex", "")).strip()
        stop_code = str(data.get("stop_code", "")).strip()
        if ok:
            st.success("Output Codex valido.")
        else:
            details = "; ".join(issues) if issues else "problemi non specificati"
            st.error(f"Output Codex non valido: {details}")
        if next_prompt:
            st.info(f"Next prompt per Codex: {next_prompt}")
            st.session_state[_CODEX_PROMPT_KEY] = next_prompt
        if stop_code == _CODEX_HITL_CODE:
            st.warning("HITL richiesto: fermare la catena e attendere supervisione.")
            st.session_state[_CODEX_HITL_KEY] = True
    except Exception as exc:  # pragma: no cover - logging happens in downstream libs
        st.error(f"Non è stato possibile validare l'output: {exc}")


def _execute_codex_cli(prompt: str) -> None:
    try:
        result = run_codex_cli(
            prompt,
            cwd=get_repo_root(),
            cmd=list(_CODEX_CLI_CMD),
            timeout_s=_CODEX_CLI_TIMEOUT_S,
        )
        st.session_state[_CODEX_OUTPUT_KEY] = result.stdout or ""
        if result.ok:
            st.success(f"Codex CLI eseguita (exit {result.exit_code}).")
        else:
            error_msg = result.error or result.stderr or "errore sconosciuto"
            st.error(f"Codex CLI fallita (exit {result.exit_code}): {error_msg}")
        if result.stderr:
            st.info(f"Codex stderr: {result.stderr}")
    except Exception as exc:
        st.error(f"Codex CLI fallita inaspettatamente: {exc}")


def _render_codex_section() -> None:
    st.subheader("Turno Codex (manuale)")
    prompt = _get_codex_prompt()
    st.text_area("Prompt per Codex", value=prompt, disabled=True)
    st.session_state.setdefault(_CODEX_OUTPUT_KEY, "")
    st.text_area(
        "Incolla qui l'output di Codex CLI",
        key=_CODEX_OUTPUT_KEY,
    )
    if st.session_state.get(_CODEX_HITL_KEY):
        st.warning("HITL richiesto: non è possibile validare altri output.")
        if st.button("Sblocca HITL (supervisore)"):
            st.session_state[_CODEX_HITL_KEY] = False
            st.success("HITL sbloccato; prosegui con il prossimo output.")
        return
    if st.button("Valida output Codex"):
        _validate_codex_output(st.session_state[_CODEX_OUTPUT_KEY])
    if st.button("Esegui Codex CLI (locale)"):
        _execute_codex_cli(prompt)


def _invoke_prototimmy_json(
    history: Iterable[Mapping[str, str]], last_user_input: str
) -> tuple[str | None, str | None]:
    settings = _load_settings()
    _maybe_consult_rosetta(settings, user_input=last_user_input)
    try:
        cfg = resolve_prototimmy_config(settings)
        transcript = _build_transcript(list(history)[:-1])
        user_payload = f"{transcript}\nUTENTE: {last_user_input}" if transcript else f"UTENTE: {last_user_input}"
        response = run_json_model(
            model=cfg.model,
            messages=(
                dict(_PROTO_JSON_SYSTEM_MESSAGE),
                {"role": "user", "content": user_payload},
            ),
            response_format=_PROTO_JSON_RESPONSE_FORMAT,
            invocation=_build_chat_invocation(
                cfg,
                component="prototimmy.chat",
                operation="prototimmy.chat.json",
                request_tag="prototimmy_chat_json",
            ),
        )
        data = cast(dict[str, Any], response.data)
        reply = str(data.get("reply_to_user", "")).strip()
        ocp_request = str(data.get("message_for_ocp", "")).strip()
        return (reply or None, ocp_request or "")
    except Exception as exc:  # pragma: no cover - logging happens in downstream libs
        st.error(f"ProtoTimmy non ha risposto: {exc}")
        return None, ""


def _invoke_prototimmy_text(prompt_text: str) -> str | None:
    try:
        settings = _load_settings()
        cfg = resolve_prototimmy_config(settings)
        response = run_text_model(
            model=cfg.model,
            messages=(
                dict(_SYSTEM_MESSAGE),
                {"role": "user", "content": prompt_text},
            ),
            invocation=_build_chat_invocation(
                cfg,
                component="prototimmy.chat",
                operation="prototimmy.chat.text",
                request_tag="prototimmy_chat_text",
            ),
        )
        return cast(str, response.text)
    except Exception as exc:
        st.error(f"ProtoTimmy non ha risposto: {exc}")
        return None


def _maybe_consult_rosetta(settings: Settings, *, user_input: str, run_id: Optional[str] = None) -> None:
    slug = getattr(settings, "client_name", None) or "prototimmy"
    try:
        client = get_rosetta_client(settings=settings, slug=slug)
    except Exception as exc:  # pragma: no cover - best effort logging
        _log_rosetta_attempt(slug=slug, run_id=run_id, enabled=False, reason="rosetta.load_failure")
        _log_rosetta_error({"slug": slug, "run_id": run_id}, exc, reason="rosetta.load_failure")
        return
    if not client:
        _log_rosetta_attempt(slug=slug, run_id=run_id, enabled=False, reason="rosetta.disabled")
        return
    try:
        assertions = [{"source": "prototimmy_chat", "text": user_input[:200]}]
        client.check_coherence(assertions=assertions, run_id=run_id)
        client.explain(assertion_id="prototimmy.placeholder", run_id=run_id)
        _log_rosetta_attempt(
            slug=slug,
            run_id=run_id,
            enabled=True,
            reason="rosetta.enabled",
            status="consulted",
        )
    except Exception as exc:
        _log_rosetta_attempt(
            slug=slug,
            run_id=run_id,
            enabled=False,
            reason="rosetta.call_failure",
            status="failed",
        )
        _log_rosetta_error({"slug": slug, "run_id": run_id}, exc, reason="rosetta.call_failure")


def _log_rosetta_error(base_extra: dict[str, Any], exc: Exception, *, reason: str) -> None:
    error_extra = dict(base_extra)
    error_extra["event"] = "prototimmy.rosetta_consult_error"
    error_extra["enabled"] = False
    error_extra["reason"] = reason
    error_extra["error_type"] = type(exc).__name__
    error_extra["error_message"] = str(exc)
    ROSETTA_HOOK_LOGGER.error(error_extra["event"], extra=error_extra)


def _log_rosetta_attempt(
    *,
    slug: str,
    run_id: Optional[str],
    enabled: bool,
    reason: str,
    status: Optional[str] = None,
) -> None:
    extra: dict[str, Any] = {
        "event": "prototimmy.rosetta_consult_attempt",
        "slug": slug,
        "enabled": enabled,
        "reason": reason,
    }
    if run_id:
        extra["run_id"] = run_id
    if status:
        extra["status"] = status
    ROSETTA_HOOK_LOGGER.info(extra["event"], extra=extra)


def _render_smoke_test() -> None:
    if not st.button("Esegui smoke test"):
        return
    try:
        result = run_prototimmy_dummy_check(verbose=False)
    except Exception as exc:
        st.error(f"Smoke test fallito: {exc}")
        return
    st.json(result)
    if result.get("ok"):
        st.success("Smoke test ProtoTimmy completato con successo.")
    else:
        st.error("Smoke test ProtoTimmy non ha superato la verifica.")


def main() -> None:
    render_chrome_then_require(
        allow_without_slug=True,
        title="ProtoTimmy Chat",
        subtitle="Chat operativa con ProtoTimmy e smoke test dedicato.",
    )
    history = _ensure_history()
    user_input = _collect_user_input()
    if user_input:
        history.append({"role": "user", "content": user_input})
        reply, ocp_request = _invoke_prototimmy_json(history, user_input)
        if reply:
            history.append({"role": "assistant", "content": reply})
        if ocp_request:
            try:
                ocp_response = _call_ocp(ocp_request)
            except Exception:
                st.error("OCP non raggiungibile")
            else:
                _render_ocp_response(ocp_response)
                summary_prompt = f"Questa è la risposta reale di OCP:\n{ocp_response}\nRiassumila per l'utente."
                summary = _invoke_prototimmy_text(summary_prompt)
                if summary:
                    history.append({"role": "assistant", "content": summary})
    _render_history(history)
    _render_smoke_test()
    _render_codex_section()


if __name__ == "__main__":
    main()


__all__ = ["main"]
