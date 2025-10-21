# scripts/kb_healthcheck.py
# Health-check: verifica uso File Search (KB) e stampa citations/file_id
# Requisiti: pip install openai>=1.52.0

import json
import os
import re
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv  # pip install python-dotenv

# carica .env (cwd o root repo) senza sovrascrivere variabili già in ambiente
load_dotenv(find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env"), override=False)

# sanificazione base URL: se manca http(s)://, rimuovi la variabile per usare il default sicuro
raw_base = (os.getenv("OPENAI_BASE_URL") or "").strip().strip("'").strip('"')
if raw_base and not re.match(r"^https?://", raw_base, flags=re.I):
    print(f"ATTENZIONE: OPENAI_BASE_URL invalida: '{raw_base}'. Userò il default https://api.openai.com/v1")
    os.environ.pop("OPENAI_BASE_URL", None)

from typing import Any, Dict, List
from openai import OpenAI

QUERY_DEFAULT = (
    "Usa la tua KB (File Search) per elencare 1-3 documenti che ritieni rilevanti. "
    "Per ciascuno dammi il nome del file e una breve citazione (max 20 parole). "
    "Se non trovi nulla, rispondi chiaramente 'NO_KB'."
)

def read_env(name: str, *alts: str) -> str:
    for k in (name, *alts):
        v = os.getenv(k)
        if v:
            return v
    return ""

def main():
    api_key = read_env("OPENAI_API_KEY")
    if not api_key:
        print("ERRORE: manca OPENAI_API_KEY nell'ambiente.")
        sys.exit(2)

    assistant_id = read_env("OBNEXT_ASSISTANT_ID", "ASSISTANT_ID")
    if not assistant_id:
        print("ERRORE: manca OBNEXT_ASSISTANT_ID/ASSISTANT_ID nell'ambiente.")
        sys.exit(2)

    user_query = " ".join(sys.argv[1:]).strip() or QUERY_DEFAULT

    client = OpenAI()  # onora OPENAI_ORG/OPENAI_PROJECT/OPENAI_BASE_URL se presenti

    # 1) Crea thread e messaggio
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_query,
    )

    # 2) Avvia run forzando l'uso di File Search (KB)
    #    response_format semplice per ridurre cause di failure dovute allo schema
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant_id,
        tool_choice={"type": "file_search"},
        response_format={"type": "text"},
        instructions="Durante QUESTA run usa attivamente File Search (KB) e, se possibile, cita i file.",
    )

    if getattr(run, "status", None) != "completed":
        # Diagnostica parlante
        last_error = getattr(run, "last_error", None)
        req = getattr(run, "required_action", None)
        print(json.dumps({
            "status": run.status,
            "run_id": getattr(run, "id", None),
            "thread_id": thread.id,
            "required_action": getattr(req, "type", None),
            "last_error_code": getattr(last_error, "code", None) if last_error else None,
            "last_error_message": getattr(last_error, "message", None) if last_error else None,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # 3) Verifica se File Search è stato effettivamente usato (guardando gli steps)
    steps = client.beta.threads.runs.steps.list(thread_id=thread.id, run_id=run.id)
    used_file_search = False
    for st in getattr(steps, "data", []) or []:
        # fallback robusto: cerco 'file_search' in una rappresentazione stringa dello step
        blob = str(getattr(st, "step_details", "")) + " " + str(st)
        if "file_search" in blob.lower():
            used_file_search = True
            break

    # 4) Leggi i messaggi e raccogli citations (file_id + eventuale quote)
    msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=10)

    citations: List[Dict[str, Any]] = []
    assistant_text_excerpt = None

    for msg in getattr(msgs, "data", []) or []:
        if getattr(msg, "role", "") != "assistant":
            continue
        for part in getattr(msg, "content", []) or []:
            if getattr(part, "type", None) == "text":
                text_obj = getattr(part, "text", None)
                value = getattr(text_obj, "value", None)
                if value and assistant_text_excerpt is None:
                    assistant_text_excerpt = value[:400]
                anns = getattr(text_obj, "annotations", []) or []
                for an in anns:
                    # Schema v2 tipico: an.type == "file_citation" e an.file_citation.file_id
                    an_type = getattr(an, "type", None)
                    fc = getattr(an, "file_citation", None)
                    if an_type == "file_citation" and fc:
                        file_id = getattr(fc, "file_id", None)
                        quote = getattr(fc, "quote", None)
                        filename = None
                        if file_id:
                            try:
                                fmeta = client.files.retrieve(file_id)
                                filename = getattr(fmeta, "filename", None)
                            except Exception:
                                pass
                        citations.append({
                            "file_id": file_id,
                            "filename": filename,
                            "quote": quote,
                        })
        if assistant_text_excerpt is not None:
            break

    result = {
        "used_file_search": used_file_search,
        "citations": citations,
        "assistant_text_excerpt": assistant_text_excerpt,
        "thread_id": thread.id,
        "run_id": getattr(run, "id", None),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Exit code utile per CI: fallisci se non ha usato File Search e non ci sono citations
    if not used_file_search and not citations:
        sys.exit(3)

if __name__ == "__main__":
    main()
