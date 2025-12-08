# SPDX-License-Identifier: GPL-3.0-only
# tools/test_prototimmy.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from pipeline.exceptions import ConfigError

# --- ensure repo root & src are on sys.path (come kb_healthcheck) ----------------
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(REPO_ROOT))

from ai.client_factory import make_openai_client  # noqa: E402
from pipeline.settings import Settings  # noqa: E402


def _get_settings() -> Settings:
    """
    Carica le Settings globali del repo, usando config/config.yaml come SSoT.
    """
    return Settings.load(REPO_ROOT)


def _retrieve_assistant(client: Any, assistant_id: str) -> Any:
    """
    Recupera i metadati dell'assistant usando la surface più moderna disponibile.

    - Preferisce client.assistants.retrieve(...)
    - Fallback su client.beta.assistants.retrieve(...) se necessario
    """
    # Preferisci surface stabile, se presente
    if hasattr(client, "assistants"):
        assistants = getattr(client, "assistants")
        if hasattr(assistants, "retrieve"):
            return assistants.retrieve(assistant_id)

    # Fallback incapsulato su beta.assistants
    beta = getattr(client, "beta", None)
    if beta is None or not hasattr(beta, "assistants"):
        raise ConfigError("Client OpenAI non espone l'API assistants (né stabile né beta).")

    return beta.assistants.retrieve(assistant_id)


def _extract_text_from_response(resp: Any) -> str:
    """
    Estrae il testo dalla Responses API con la stessa logica usata altrove:
    - prima cerca in resp.output[*].text.value con type == "output_text"
    - fallback su resp.output_text (se presente)
    """
    text: Optional[str] = None

    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", "") == "output_text":
            txt = getattr(getattr(item, "text", None), "value", None)
            if isinstance(txt, str) and txt.strip():
                text = txt.strip()
                break

    if not text:
        fallback = getattr(resp, "output_text", None)
        if isinstance(fallback, str) and fallback.strip():
            text = fallback.strip()

    return text or ""


def _resolve_assistant_id(settings: Settings, yaml_key: str, label: str) -> str:
    """
    Risolve un assistant_id a partire dal path YAML *.assistant_id_env,
    usando la stessa logica già usata per protoTimmy.
    """
    try:
        assistant_id = settings.resolve_env_ref(
            yaml_key,
            required=True,
        )
    except ConfigError as exc:
        print(
            f"[ERRORE CONFIG] Problema nel risolvere {yaml_key} "
            f"({label}) da .env: {exc}"
        )
        raise SystemExit(1)

    if not assistant_id:
        print(
            f"[ERRORE CONFIG] {label} non risolto: controlla che {yaml_key} "
            "punti alla variabile d'ambiente corretta e che sia valorizzata in .env"
        )
        raise SystemExit(1)

    return assistant_id


def main() -> None:
    # 1) Carico config + segreti usando l'infrastruttura esistente
    try:
        settings = _get_settings()
    except ConfigError as exc:
        print(f"[ERRORE CONFIG] Impossibile caricare config/config.yaml: {exc}")
        raise SystemExit(1)

    # 2) Risolvo l'ID di protoTimmy, Planner Assistant e OCP Executor
    prototimmy_id = _resolve_assistant_id(
        settings,
        "ai.prototimmy.assistant_id_env",
        "PROTOTIMMY_ID",
    )
    planner_id = _resolve_assistant_id(
        settings,
        "ai.planner_assistant.assistant_id_env",
        "PLANNER_ASSISTANT_ID",
    )
    ocp_executor_id = _resolve_assistant_id(
        settings,
        "ai.ocp_executor.assistant_id_env",
        "OCP_EXECUTOR_ASSISTANT_ID",
    )

    # 3) Client OpenAI usando la factory centralizzata (gestisce .env, timeout, ecc.)
    try:
        client = make_openai_client()
    except Exception as exc:  # pragma: no cover - diagnostico
        print(f"[ERRORE OPENAI] Impossibile inizializzare il client OpenAI: {exc}")
        raise SystemExit(1)

    # 4) Recupero metadati dei tre assistant (facoltativo ma utile per debug)
    try:
        proto_meta = _retrieve_assistant(client, prototimmy_id)
        planner_meta = _retrieve_assistant(client, planner_id)
        ocp_meta = _retrieve_assistant(client, ocp_executor_id)
    except Exception as exc:
        print(f"[ERRORE API] Impossibile recuperare uno degli assistant: {exc}")
        raise SystemExit(1)

    proto_model = getattr(proto_meta, "model", None) or "gpt-4.1"
    planner_model = getattr(planner_meta, "model", None) or "gpt-4.1"
    ocp_model = getattr(ocp_meta, "model", None) or "gpt-4.1"

    print("✅ protoTimmy raggiungibile")
    print(f"   id:    {proto_meta.id}")
    print(f"   nome:  {getattr(proto_meta, 'name', '')}")
    print(f"   model: {proto_model}")

    print("✅ Planner Assistant raggiungibile")
    print(f"   id:    {planner_meta.id}")
    print(f"   nome:  {getattr(planner_meta, 'name', '')}")
    print(f"   model: {planner_model}")

    print("✅ OCP Executor raggiungibile")
    print(f"   id:    {ocp_meta.id}")
    print(f"   nome:  {getattr(ocp_meta, 'name', '')}")
    print(f"   model: {ocp_model}")

    # 5) Ping minimale via Responses API per protoTimmy (con model, non assistant_id)
    try:
        resp_ping = client.responses.create(
            model=proto_model,
            input=[
                {
                    "role": "user",
                    "content": (
                        "Ping di test da timmy-kb-acme (protoTimmy). "
                        "Rispondi solo con la parola 'pong'."
                    ),
                }
            ],
            temperature=0,
        )
    except AttributeError as exc:
        print(
            "[ERRORE API] Client OpenAI non supporta l'API Responses "
            f"(AttributeError: {exc})"
        )
        raise SystemExit(1)
    except Exception as exc:
        print(f"[ERRORE API] Chiamata Responses fallita (ping protoTimmy): {exc}")
        raise SystemExit(1)

    text_ping = _extract_text_from_response(resp_ping)

    if not text_ping:
        print("[WARN] Nessun testo restituito dalla Responses API (ping).")
        raise SystemExit(1)

    print(f"   risposta ping protoTimmy: {text_ping!r}")

    if text_ping.strip().lower() != "pong":
        print("[WARN] La risposta al ping non è 'pong' come richiesto.")
        raise SystemExit(1)

    # 6) Giro completo: protoTimmy -> Planner Assistant -> OCP Executor

    print("\n▶ Avvio giro completo: protoTimmy → Planner Assistant → OCP Executor")

    # 6.1 protoTimmy genera un messaggio di test
    try:
        resp_proto = client.responses.create(
            model=proto_model,
            input=[
                {
                    "role": "user",
                    "content": (
                        "Test di integrazione. Genera una breve frase che inizi con "
                        "'PROTO:' e non aggiungere spiegazioni."
                    ),
                }
            ],
            temperature=0,
        )
    except Exception as exc:
        print(f"[ERRORE API] Chiamata Responses fallita (protoTimmy → Planner): {exc}")
        raise SystemExit(1)

    proto_text = _extract_text_from_response(resp_proto).strip()
    print(f"   output protoTimmy: {proto_text!r}")

    if not proto_text.startswith("PROTO:"):
        print("[WARN] L'output di protoTimmy non inizia con 'PROTO:' come atteso.")

    # 6.2 Planner Assistant riceve il testo e aggiunge ' PLANNER_OK'
    try:
        resp_planner = client.responses.create(
            model=planner_model,
            input=[
                {
                    "role": "user",
                    "content": (
                        "Test di integrazione Planner.\n"
                        "Hai ricevuto questo input da protoTimmy:\n"
                        f"{proto_text}\n\n"
                        "Aggiungi alla fine della stringa esattamente ' PLANNER_OK' "
                        "e restituisci SOLO la stringa risultante, senza spiegazioni."
                    ),
                }
            ],
            temperature=0,
        )
    except Exception as exc:
        print(f"[ERRORE API] Chiamata Responses fallita (Planner → OCP): {exc}")
        raise SystemExit(1)

    planner_text = _extract_text_from_response(resp_planner).strip()
    print(f"   output Planner Assistant: {planner_text!r}")

    if not planner_text.endswith("PLANNER_OK"):
        print("[WARN] L'output del Planner non termina con 'PLANNER_OK' come atteso.")

    # 6.3 OCP Executor riceve il testo e aggiunge ' OCP_OK'
    try:
        resp_ocp = client.responses.create(
            model=ocp_model,
            input=[
                {
                    "role": "user",
                    "content": (
                        "Test di integrazione OCP Executor.\n"
                        "Hai ricevuto questo input dal Planner Assistant:\n"
                        f"{planner_text}\n\n"
                        "Aggiungi alla fine della stringa esattamente ' OCP_OK' "
                        "e restituisci SOLO la stringa risultante, senza spiegazioni."
                    ),
                }
            ],
            temperature=0,
        )
    except Exception as exc:
        print(f"[ERRORE API] Chiamata Responses fallita (OCP finale): {exc}")
        raise SystemExit(1)

    ocp_text = _extract_text_from_response(resp_ocp).strip()
    print(f"   output OCP Executor: {ocp_text!r}")

    if not ocp_text.endswith("OCP_OK"):
        print("[WARN] L'output dell'OCP Executor non termina con 'OCP_OK' come atteso.")
        raise SystemExit(1)

    print("\n✅ Giro completo protoTimmy → Planner Assistant → OCP Executor completato con successo.")


if __name__ == "__main__":
    main()
