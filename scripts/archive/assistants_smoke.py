#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-only
# scripts/archive/assistants_smoke.py
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def main() -> int:
    try:
        # carica .env se presente
        try:
            from dotenv import find_dotenv, load_dotenv  # type: ignore

            path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[2] / ".env")
            if path:
                load_dotenv(path, override=False)
        except Exception:
            pass

        from ai.client_factory import make_openai_client  # usa lo stesso factory della UI
    except Exception as e:
        print(f"ERRORE import: {e}")
        return 2

    from pipeline.env_utils import get_env_var

    asst = get_env_var("OBNEXT_ASSISTANT_ID", default=None) or get_env_var("ASSISTANT_ID", default=None)
    if not asst:
        print("ERRORE: manca OBNEXT_ASSISTANT_ID/ASSISTANT_ID")
        return 2

    client = make_openai_client()
    # 1) thread
    th = client.beta.threads.create()
    # 2) messaggio user minimale
    prompt = 'Restituisci SOLO JSON: {"ok": true, "note": "smoke"}'
    client.beta.threads.messages.create(thread_id=th.id, role="user", content=prompt)
    # 3) run con response_format=json_schema minimale
    run = client.beta.threads.runs.create_and_poll(
        thread_id=th.id,
        assistant_id=asst,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "smoke",
                "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                "strict": True,
            },
        },
        instructions="Ignora File Search e tool. Usa SOLO il messaggio utente.",
    )
    print(f"Run status: {run.status}")
    msgs = client.beta.threads.messages.list(thread_id=th.id, order="desc", limit=1)
    out = None
    for m in getattr(msgs, "data", []):
        for c in getattr(m, "content", []):
            t = getattr(c, "type", None)
            if t in ("text", "output_text"):
                out = getattr(getattr(c, "text", None), "value", None)
                if out:
                    break
        if out:
            break
    if not out:
        print("ERRORE: nessun output")
        return 3
    print("Output:", out)
    # deve essere JSON
    json.loads(out)
    print("Assistants smoke: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
