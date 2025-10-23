# scripts/kb_healthcheck_responses.py
# Verifica l'uso reale della KB (File Search) con Responses API, mostrando citations.
# Requisiti: openai>=2.3.0, python-dotenv

import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI

def load_env():
    load_dotenv(find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env"), override=False)
    # Sanifica base URL: se manca http/https, rimuovi per usare il default
    raw_base = (os.getenv("OPENAI_BASE_URL") or "").strip().strip("'").strip('"')
    if raw_base and not re.match(r"^https?://", raw_base, flags=re.I):
        print(f"ATTENZIONE: OPENAI_BASE_URL invalida: '{raw_base}'. Userò il default https://api.openai.com/v1")
        os.environ.pop("OPENAI_BASE_URL", None)

def read_env(*names):
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None

def resolve_vector_store_id(client: OpenAI, maybe_id: str | None, assistant_id: str | None) -> list[str]:
    # 1) se l'utente l'ha passato via env, usalo
    if maybe_id:
        return [maybe_id]
    # 2) altrimenti prova a leggerlo dall'assistente (tool_resources.file_search.vector_store_ids)
    if assistant_id:
        try:
            a = client.beta.assistants.retrieve(assistant_id)
            fs = getattr(getattr(a, "tool_resources", None), "file_search", None)
            vss = getattr(fs, "vector_store_ids", None) if fs else None
            if vss:
                return list(vss)
        except Exception as e:
            print(f"ATTENZIONE: non riesco a leggere l'assistente {assistant_id}: {e}")
    return []

def extract_citations(resp) -> dict:
    used = False
    cits = []
    excerpt = None

    # Nei payload moderni, le citations compaiono in output -> output_text.annotations
    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", "") == "output_text":
            text_obj = getattr(item, "text", None)
            value = getattr(text_obj, "value", None)
            if value and excerpt is None:
                excerpt = value[:500]
            anns = getattr(text_obj, "annotations", []) or []
            for an in anns:
                if getattr(an, "type", None) == "file_citation":
                    used = True
                    cits.append({
                        "file_id": getattr(an, "file_id", None),
                        "filename": getattr(an, "filename", None),
                        "index": getattr(an, "index", None),
                        "quote": getattr(an, "quote", None),
                    })
    return {"used_file_search": used, "citations": cits, "text_excerpt": excerpt}

def main():
    load_env()
    api_key = read_env("OPENAI_API_KEY")
    if not api_key:
        print("ERRORE: manca OPENAI_API_KEY (.env o ambiente).")
        sys.exit(2)

    assistant_id = read_env("OBNEXT_ASSISTANT_ID", "ASSISTANT_ID")
    model = os.getenv("KB_HEALTH_MODEL", "gpt-4o-2024-08-06")
    user_query = " ".join(sys.argv[1:]).strip() or "Usa la KB per citare 1-2 documenti con breve frase."

    client = OpenAI()

    # Risolvi vector store IDs
    vs_env = read_env("KB_VECTOR_STORE_ID")
    vector_store_ids = resolve_vector_store_id(client, vs_env, assistant_id)
    if not vector_store_ids:
        print(
            "ERRORE: nessuna vector store trovata. Imposta KB_VECTOR_STORE_ID nello .env "
            "oppure collega una store all'Assistant."
        )
        sys.exit(3)

    # Responses API + File Search (forzato)
    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": user_query}],
        tools=[{
            "type": "file_search",
            "file_search": {"vector_store_ids": vector_store_ids, "max_num_results": 4}
        }],
        tool_choice="file_search",
        response_format={"type": "text"},
    )

    out = {
        "response_id": getattr(resp, "id", None),
        "vector_store_ids": vector_store_ids,
        **extract_citations(resp),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    # Esci con codice 0 se la KB risulta usata o ci sono citations
    sys.exit(0 if out["used_file_search"] or out["citations"] else 4)

if __name__ == "__main__":
    main()
