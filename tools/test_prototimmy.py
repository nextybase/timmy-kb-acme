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


def main() -> None:
    # 1) Carico config + segreti usando l'infrastruttura esistente
    try:
        settings = _get_settings()
    except ConfigError as exc:
        print(f"[ERRORE CONFIG] Impossibile caricare config/config.yaml: {exc}")
        raise SystemExit(1)

    # 2) Risolvo l'ID di protoTimmy partendo da ai.prototimmy.assistant_id_env
    try:
        prototimmy_id = settings.resolve_env_ref(
            "ai.prototimmy.assistant_id_env",
            required=True,
        )
    except ConfigError as exc:
        print(
            "[ERRORE CONFIG] Problema nel risolvere ai.prototimmy.assistant_id_env "
            f"da .env: {exc}"
        )
        raise SystemExit(1)

    if not prototimmy_id:
        print(
            "[ERRORE CONFIG] PROTOTIMMY_ID non risolto: controlla che "
            "ai.prototimmy.assistant_id_env punti a PROTOTIMMY_ID "
            "e che PROTOTIMMY_ID sia valorizzato in .env"
        )
        raise SystemExit(1)

    # 3) Client OpenAI usando la factory centralizzata (gestisce .env, timeout, ecc.)
    try:
        client = make_openai_client()
    except Exception as exc:  # pragma: no cover - diagnostico
        print(f"[ERRORE OPENAI] Impossibile inizializzare il client OpenAI: {exc}")
        raise SystemExit(1)

    # 4) Recupero i metadati dell'assistant (senza usare threads legacy)
    try:
        assistant = _retrieve_assistant(client, prototimmy_id)
    except Exception as exc:
        print(
            f"[ERRORE API] Impossibile recuperare l'assistant {prototimmy_id}: {exc}"
        )
        raise SystemExit(1)

    print("✅ protoTimmy raggiungibile")
    print(f"   id:    {assistant.id}")
    print(f"   nome:  {getattr(assistant, 'name', '')}")
    print(f"   model: {getattr(assistant, 'model', '')}")

    # 5) Ping minimale via Responses API (nessun uso di beta.threads.*)
    model_for_ping = getattr(assistant, "model", None) or "gpt-4.1"

    try:
        resp = client.responses.create(
            model=model_for_ping,
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
        print(f"[ERRORE API] Chiamata Responses fallita: {exc}")
        raise SystemExit(1)

    text = _extract_text_from_response(resp)

    if not text:
        print("[WARN] Nessun testo restituito dalla Responses API.")
        raise SystemExit(1)

    print(f"   risposta assistant: {text!r}")

    # opzionale: se vuoi proprio essere pignolo sulla risposta
    if text.strip().lower() != "pong":
        print("[WARN] La risposta non è 'pong' come richiesto.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
