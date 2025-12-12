# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/prototimmy_chat.py
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from ai.check import run_prototimmy_dummy_check
from ai.config import resolve_ocp_executor_config, resolve_prototimmy_config
from ai.responses import run_text_model
from pipeline.settings import Settings
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

_TRANSCRIPT_MAX_LINES = 20


def _load_settings() -> Settings:
    return Settings.load(get_repo_root())


def _ensure_history() -> list[dict[str, str]]:
    history = st.session_state.setdefault(_SESSION_KEY, [])
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


def _extract_ocp_request(text: str) -> str | None:
    for line in text.splitlines():
        if "message_for_ocp" in line.lower():
            parts = line.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None


def _call_ocp(message: str) -> str:
    settings = _load_settings()
    cfg = resolve_ocp_executor_config(settings)
    response = run_text_model(
        model=cfg.model,
        messages=(
            dict(_SYSTEM_MESSAGE),
            {"role": "user", "content": f"Rispondi con i dati richiesti: {message}"},
        ),
    )
    return response.text


def _render_ocp_response(text: str) -> None:
    with st.expander("Risposta OCP", expanded=False):
        st.write(text)


def _invoke_model(history: Iterable[Mapping[str, str]], last_user_input: str) -> tuple[str | None, str | None]:
    try:
        settings = _load_settings()
        cfg = resolve_prototimmy_config(settings)
        transcript = _build_transcript(list(history)[:-1])
        user_payload = f"{transcript}\nUTENTE: {last_user_input}" if transcript else f"UTENTE: {last_user_input}"
        response = run_text_model(
            model=cfg.model,
            messages=(
                dict(_SYSTEM_MESSAGE),
                {"role": "user", "content": user_payload},
            ),
        )
        ocp_request = _extract_ocp_request(response.text)
        return response.text, ocp_request
    except Exception as exc:  # pragma: no cover - logging happens in downstream libs
        st.error(f"ProtoTimmy non ha risposto: {exc}")
        return None, None


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
        reply, ocp_request = _invoke_model(history, user_input)
        final_reply = reply
        if reply and ocp_request:
            try:
                ocp_response = _call_ocp(ocp_request)
            except Exception:
                st.error("OCP non raggiungibile")
            else:
                _render_ocp_response(ocp_response)
                summary_prompt = f"Questa è la risposta reale di OCP:\n{ocp_response}\nRiassumila per l'utente."
                extended_history = history + [{"role": "user", "content": summary_prompt}]
                final_reply, _ = _invoke_model(extended_history, summary_prompt)
        if final_reply:
            history.append({"role": "assistant", "content": final_reply})
    _render_history(history)
    _render_smoke_test()


if __name__ == "__main__":
    main()


__all__ = ["main"]
