# SPDX-License-Identifier: GPL-3.0-only
# scripts/vision_alignment_check.py
# Health-check 1:1 con il flusso Vision (Assistants v2), robusto e “sempre verboso”.
# Compatibile con openai==2.3.0. Requisiti: python-dotenv.

import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv, find_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pipeline.env_utils import get_env_var

def _print_json(payload: Dict[str, Any], exit_code: int = None):
    try:
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    except Exception:
        # fallback minimale se la console ha problemi di encoding
        print(str(payload), flush=True)
    if exit_code is not None:
        sys.exit(exit_code)

def _load_env_and_sanitize():
    load_dotenv(find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env"), override=False)
    raw_base = (get_env_var("OPENAI_BASE_URL", default="") or "").strip().strip("'").strip('"')
    if raw_base and not re.match(r"^https?://", raw_base, flags=re.I):
        os.environ.pop("OPENAI_BASE_URL", None)

def _env(*names: str) -> str | None:
    for n in names:
        v = get_env_var(n, default=None)
        if v:
            return v
    return None

def main():
    from openai import OpenAI

    # 0) ENV
    _load_env_and_sanitize()
    if not _env("OPENAI_API_KEY"):
        _print_json({"status": "error", "reason": "missing_api_key"}, 2)

    assistant_id = _env("OBNEXT_ASSISTANT_ID", "ASSISTANT_ID")
    if not assistant_id:
        _print_json({"status": "error", "reason": "missing_assistant_id"}, 2)

    use_kb = (_env("VISION_USE_KB") or "1").strip().lower() not in {"0", "false", "no", "off"}
    # 1) Import schema reale dal modulo Vision
    #    Aggiungiamo src al PYTHONPATH per rispecchiare l’app
    try:
        from semantic.vision_provision import _load_vision_schema  # stesso loader della tua app
    except Exception as e:
        _print_json({"status": "error", "reason": "schema_import_failed", "detail": str(e)}, 2)

    client = OpenAI()

    # 2) Pre-flight Assistant
    try:
        asst = client.beta.assistants.retrieve(assistant_id)
        asst_model = getattr(asst, "model", "") or ""
    except Exception as e:
        _print_json({"status": "error", "reason": "assistant_retrieve_failed", "detail": str(e)}, 2)

    supports_structured = ("gpt-4o-2024-08-06" in asst_model) or ("gpt-4o-mini" in asst_model)

    # 3) Thread & messaggi (blocchetto minimo, come Vision)
    TEST_BLOCK = (
        "[Vision]\n"
        "Diventare leader locale nell'adozione etica dell'AI per PMI siciliane.\n\n"
        "[Mission]\n"
        "Formare team interni e integrare micro-agenti AI nei processi core.\n\n"
        "[Goal]\n"
        "Aumentare produttività del 25% in 12 mesi con progetti pilota iterativi.\n\n"
        "[Framework etico]\n"
        "Human-in-the-Loop, tracciabilità, minimizzazione dei bias, AI literacy.\n\n"
        "[Contesto Operativo]\n"
        (
            "Settore servizi/manifattura regionale, lingue di lavoro: italiano e inglese, normative: GDPR, AI Act UE, "
            "policy interne di data governance.\n"
        )
    )

    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=TEST_BLOCK)
    except Exception as e:
        _print_json({"status": "error", "reason": "thread_or_message_failed", "detail": str(e)}, 2)

    # 4) response_format & tool_choice come Vision (schema reale)
    response_format = (
        {
            "type": "json_schema",
            "json_schema": {
                "name": "VisionOutput",
                "schema": _load_vision_schema(),  # << lo stesso schema dell’app
                "strict": True,
            },
        }
        if supports_structured
        else {"type": "json_object"}
    )
    run_instructions = (
        "Durante QUESTA run puoi usare **File Search** (KB collegata all'assistente) "
        "per integrare/validare i contenuti. Dai priorità al blocco Vision qui sopra. "
        "Produci SOLO il JSON richiesto, niente testo extra."
        if use_kb else
        "Durante QUESTA run: ignora File Search e qualsiasi risorsa esterna; "
        "usa esclusivamente il blocco Vision qui sopra. "
        "Produci SOLO il JSON richiesto, niente testo extra."
    )
    tool_choice = {"type": "file_search"} if use_kb else "auto"

    # 5) Run
    try:
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
            response_format=response_format,
            instructions=run_instructions,
            tool_choice=tool_choice,
        )
    except Exception as e:
        _print_json({
            "status": "error",
            "reason": "run_create_failed",
            "detail": str(e),
            "assistant_model": asst_model
        }, 2)

    status = getattr(run, "status", None)
    if status != "completed":
        last_error = getattr(run, "last_error", None)
        req = getattr(run, "required_action", None)
        _print_json({
            "status": status or "n/d",
            "assistant_model": asst_model,
            "required_action": getattr(req, "type", None),
            "last_error_code": getattr(last_error, "code", None) if last_error else None,
            "last_error_message": getattr(last_error, "message", None) if last_error else None,
            "thread_id": thread.id,
            "run_id": getattr(run, "id", None),
            "used_kb": use_kb,
            "response_format": "json_schema" if supports_structured else "json_object",
        }, 1)

    # 6) Steps & citations
    try:
        steps = client.beta.threads.runs.steps.list(thread_id=thread.id, run_id=run.id)
    except Exception:
        steps = None
    used_file_search = False
    if steps:
        for st in getattr(steps, "data", []) or []:
            if "file_search" in (str(getattr(st, "step_details", "")) + " " + str(st)).lower():
                used_file_search = True
                break

    try:
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=10)
    except Exception as e:
        _print_json({"status": "error", "reason": "messages_list_failed", "detail": str(e)}, 2)

    text = None
    citations = []
    for msg in getattr(msgs, "data", []) or []:
        if getattr(msg, "role", "") != "assistant":
            continue
        for part in (getattr(msg, "content", []) or []):
            if getattr(part, "type", None) == "output_text":
                t = getattr(part, "text", None)
                if t and getattr(t, "value", None) and text is None:
                    text = t.value
                for an in (getattr(t, "annotations", []) or []):
                    if getattr(an, "type", "") == "file_citation":
                        citations.append({
                            "file_id": getattr(an, "file_id", None),
                            "filename": getattr(an, "filename", None),
                            "quote": getattr(an, "quote", None),
                        })
            elif getattr(part, "type", None) == "text":
                t = getattr(part, "text", None)
                if t and getattr(t, "value", None) and text is None:
                    text = t.value
                for an in (getattr(t, "annotations", []) or []):
                    if getattr(an, "type", "") == "file_citation":
                        citations.append({
                            "file_id": getattr(an, "file_id", None),
                            "filename": getattr(an, "filename", None),
                            "quote": getattr(an, "quote", None),
                        })
        if text:
            break

    out = {
        "status": status,
        "assistant_model": asst_model,
        "used_kb": use_kb,
        "used_file_search": used_file_search,
        "response_format": "json_schema" if supports_structured else "json_object",
        "citations": citations,
        "text_excerpt": (text or "")[:400] if text else None,
        "thread_id": thread.id,
        "run_id": getattr(run, "id", None),
    }
    _print_json(out, 0 if (not use_kb or used_file_search or citations) else 4)

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        _print_json({
            "status": "exception",
            "error": str(e),
            "traceback": traceback.format_exc(limit=5)
        }, 2)
