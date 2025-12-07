# SPDX-License-Identifier: GPL-3.0-only
# tools/test_prototimmy.py
from __future__ import annotations

import sys
from pathlib import Path

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

    # 4) Recupero i metadati dell'assistant
    try:
        assistant = client.beta.assistants.retrieve(prototimmy_id)
    except Exception as exc:
        print(
            f"[ERRORE API] Impossibile recuperare l'assistant {prototimmy_id}: {exc}"
        )
        raise SystemExit(1)

    print("✅ protoTimmy raggiungibile")
    print(f"   id:    {assistant.id}")
    print(f"   nome:  {getattr(assistant, 'name', '')}")
    print(f"   model: {getattr(assistant, 'model', '')}")

    # 5) Ping minimale: creiamo un thread e chiediamo “pong”
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="Ping di test da timmy-kb-acme (protoTimmy). "
        "Rispondi solo con la parola 'pong'.",
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )

    if run.status != "completed":
        print(f"[WARN] Run non completata, stato={run.status}")
        raise SystemExit(1)

    msgs = client.beta.threads.messages.list(
        thread_id=thread.id,
        order="desc",
        limit=5,
    )

    text = ""
    for msg in getattr(msgs, "data", []) or []:
        if getattr(msg, "role", "") != "assistant":
            continue
        for part in getattr(msg, "content", None) or []:
            t = getattr(part, "type", None)
            if t in ("text", "output_text"):
                txt = getattr(getattr(part, "text", None), "value", None)
                if isinstance(txt, str) and txt.strip():
                    text = txt.strip()
                    break
        if text:
            break

    print(f"   risposta assistant: {text!r}")


if __name__ == "__main__":
    main()
