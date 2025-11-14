# SPDX-License-Identifier: GPL-3.0-only
# scripts/vision_alignment_check.py
# Health-check 1:1 con il flusso Vision (Responses API), robusto e molto verboso.
# Richiede:
#   - python-dotenv
#   - una versione recente di openai-python che espone `client.responses.create`

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv, find_dotenv


# -------------------------------------------------
# Rilevamento robusto della root del repo
# -------------------------------------------------
def _detect_repo_root() -> Path:
    """
    Trova la root del repo risalendo le cartelle finché non vede `src/`.
    Funziona sia se il file è in `scripts/` che in `scripts/archive/`.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "src").is_dir():
            return candidate

    # Fallback: parent di `scripts/`, se presente
    for candidate in here.parents:
        if candidate.name == "scripts":
            return candidate.parent

    # Ultimo fallback: 1 livello sopra il file
    return here.parents[1]


ROOT = _detect_repo_root()
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pipeline.env_utils import get_env_var  # noqa: E402
from pipeline.logging_utils import get_structured_logger  # noqa: E402
from pipeline.settings import Settings as PipelineSettings
LOGGER = get_structured_logger("vision.alignment_check")


def _print_json(payload: Dict[str, Any], exit_code: Optional[int] = None) -> None:
    try:
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    except Exception:
        # fallback minimale se la console ha problemi di encoding
        print(str(payload), flush=True)
    if exit_code is not None:
        sys.exit(exit_code)


def _load_env_and_sanitize() -> None:
    """
    Carica .env e pulisce eventuali OPENAI_BASE_URL senza schema http/https.
    Cerca prima con find_dotenv(), poi in ROOT/.env.
    """
    env_path = find_dotenv(usecwd=True) or str(ROOT / ".env")
    load_dotenv(env_path, override=False)

    raw_base = (get_env_var("OPENAI_BASE_URL", default="") or "").strip().strip("'").strip('"')
    if raw_base and not re.match(r"^https?://", raw_base, flags=re.I):
        # Evita errori tipo "Invalid URL 'api.openai.com/v1'..."
        os.environ.pop("OPENAI_BASE_URL", None)


def _env(*names: str) -> Optional[str]:
    for n in names:
        v = get_env_var(n, default=None)
        if v:
            return v
    return None


def main() -> None:
    from openai import OpenAI  # import locale per evitare hard-dependency a import-time

    # 0) ENV
    _load_env_and_sanitize()

    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        _print_json({"status": "error", "reason": "missing_api_key"}, 2)

    # Nota: con Responses non è strettamente necessario l'assistant_id,
    # ma lo manteniamo per continuità / tracciabilità.
    settings = None
    try:
        settings = PipelineSettings.load(ROOT)
    except Exception:
        settings = None

    if settings and settings.vision_assistant_env:
        assistant_env_name = settings.vision_assistant_env
        assistant_configured = True
    else:
        assistant_env_name = "OBNEXT_ASSISTANT_ID"
        assistant_configured = False

    assistant_id = None
    assistant_id_source = "missing"
    assistant_env = "missing"
    assistant_env_source = "missing"
    for candidate in (assistant_env_name, "ASSISTANT_ID"):
        value = get_env_var(candidate, default=None)
        if value:
            assistant_id = value
            if candidate == "ASSISTANT_ID":
                assistant_id_source = "default"
            elif assistant_configured and settings and candidate == assistant_env_name:
                assistant_id_source = "config"
            else:
                assistant_id_source = "env"
            break

    if assistant_id:
        assistant_env = candidate
        assistant_env_source = assistant_id_source

    LOGGER.info(
        "vision_alignment_check.assistant_id",
        extra={
            "value": assistant_id,
            "source": assistant_id_source,
            "assistant_env": assistant_env,
            "assistant_env_source": assistant_env_source,
        },
    )

    # Modello da usare per Vision. Se non specificato, fallback ragionevole.
    model = _env("VISION_MODEL", "OPENAI_MODEL")
    if not model and settings and settings.vision_model:
        model = settings.vision_model
    model = model or "gpt-4o-mini-2024-07-18"

    use_kb_env = _env("VISION_USE_KB")
    use_kb_from_env: Optional[bool] = None
    if use_kb_env is not None:
        use_kb_from_env = use_kb_env.strip().lower() not in {"0", "false", "no", "off"}

    use_kb_defaults_to = settings.vision_settings.use_kb if settings else True
    use_kb = use_kb_from_env if use_kb_from_env is not None else use_kb_defaults_to
    use_kb_source = "env" if use_kb_from_env is not None else ("config" if settings else "default")
    LOGGER.info("vision_alignment_check.use_kb", extra={"value": use_kb, "source": use_kb_source})

    # 1) Import schema reale dal modulo Vision
    try:
        # stesso loader usato dall’app
        from semantic.vision_provision import _load_vision_schema  # type: ignore[attr-defined]
    except Exception as e:
        _print_json(
            {
                "status": "error",
                "reason": "schema_import_failed",
                "detail": str(e),
            },
            2,
        )

    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    if settings:
        openai_cfg = settings.openai_settings
        client_kwargs["timeout"] = float(openai_cfg.timeout)
        client_kwargs["max_retries"] = int(openai_cfg.max_retries)
        if openai_cfg.http2_enabled:
            client_kwargs["http2"] = True
    client = OpenAI(**client_kwargs)

    # 2) Blocchetto Vision minimo (come UI)
    TEST_BLOCK = (
        "[Vision]\n"
        "Diventare leader locale nell'adozione etica dell'AI per PMI siciliane.\n\n"
        "[Mission]\n"
        "Formare team interni e integrare micro-agenti AI nei processi core.\n\n"
        "[Goal]\n"
        "Aumentare produttività del 25% in 12 mesi con progetti pilota iterativi.\n\n"
        "[Framework etico]\n"
        "Human-in-the-Loop, tracciabilità, minimizzazione dei bias, AI literacy.\n\n"
        "[Prodotto/Azienda]\n"
        "Servizi consulenziali e piattaforma Nexty/Timmy per onboarding AI.\n\n"
        "[Mercato]\n"
        "PMI di servizi/manifattura nel territorio regionale, canale B2B diretto.\n"
    )

    # 3) Structured output: JSON Schema reale di Vision
    try:
        schema = _load_vision_schema()  # deve restituire un dict JSON Schema
    except Exception as e:
        _print_json(
            {
                "status": "error",
                "reason": "vision_schema_failed",
                "detail": str(e),
            },
            2,
        )

    strict_output_source = "config" if settings else "default"
    strict_output = bool(settings.vision_settings.strict_output) if settings else True
    LOGGER.info(
        "vision_alignment_check.strict_output",
        extra={"value": strict_output, "source": strict_output_source},
    )
    text_cfg: Dict[str, Any] | None = None
    if strict_output:
        text_cfg = {
            "format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "VisionOutput",
                    "schema": schema,
                    "strict": True,
                },
            }
        }

    # 4) Tools / File Search (se abilitato)
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Any = "none"

    if use_kb:
        # Se il progetto è configurato con una KB / Vector Store di default,
        # basta dichiarare il tool `file_search`.
        tools = [
            {
                "type": "file_search",
                # Se vuoi forzare un Vector Store specifico:
                # "vector_store_ids": ["vs_..."],
            }
        ]
        tool_choice = {"type": "file_search"}

    # Istruzioni per questa run (equivalente del vecchio `instructions` Assistants)
    run_instructions = (
        "Durante QUESTA run puoi usare File Search (KB collegata al progetto/assistente) "
        "per integrare e validare i contenuti. Dai priorità al blocco Vision qui sopra. "
        "Produci SOLO il JSON richiesto, niente testo extra."
        if use_kb
        else "Durante QUESTA run: ignora File Search e qualsiasi risorsa esterna; "
        "usa esclusivamente il blocco Vision qui sopra. "
        "Produci SOLO il JSON richiesto, niente testo extra."
    )

    metadata = {"source": "vision_alignment_check"}
    if assistant_id:
        metadata["assistant_id"] = assistant_id

    request_kwargs: Dict[str, Any] = {
        "model": model,
        "input": TEST_BLOCK,
        "instructions": run_instructions,
        "tools": tools,
        "tool_choice": tool_choice,
        "metadata": metadata,
    }
    if text_cfg:
        request_kwargs["text"] = text_cfg

    # 5) Chiamata Responses API
    try:
        response = client.responses.create(**request_kwargs)
    except Exception as e:
        _print_json(
            {
                "status": "error",
                "reason": "responses_create_failed",
                "detail": str(e),
                "assistant_model": model,
            },
            2,
        )

    # 6) Analisi output: testo, citazioni, file_search
    output_items = getattr(response, "output", []) or []
    text: Optional[str] = None
    citations: List[Dict[str, Any]] = []
    used_file_search = False
    message_status: Optional[str] = None

    for out in output_items:
        o_type = getattr(out, "type", None)

        if o_type == "file_search_call":
            used_file_search = True

        if o_type == "message":
            message_status = getattr(out, "status", None) or message_status

            for content in getattr(out, "content", []) or []:
                c_type = getattr(content, "type", None)
                if c_type != "output_text":
                    continue

                raw_text = getattr(content, "text", None)
                if hasattr(raw_text, "value"):
                    value = getattr(raw_text, "value", None)
                else:
                    value = raw_text

                if value is not None and text is None:
                    text = str(value)

                for an in getattr(content, "annotations", []) or []:
                    if getattr(an, "type", "") == "file_citation":
                        citations.append(
                            {
                                "file_id": getattr(an, "file_id", None),
                                "filename": getattr(an, "filename", None),
                                "quote": getattr(an, "quote", None),
                            }
                        )

            # Se abbiamo già estratto il testo principale, possiamo fermarci
            if text is not None:
                break

    # Fallback di status se non presente
    status = message_status or "completed"

    out: Dict[str, Any] = {
        "status": status,
        "assistant_model": getattr(response, "model", None) or model,
        "used_kb": use_kb,
        "used_file_search": used_file_search or bool(citations),
        "assistant_id": assistant_id,
        "assistant_id_source": assistant_id_source,
        "assistant_env": assistant_env,
        "assistant_env_source": assistant_env_source,
        "response_format": "json_schema" if strict_output else "text",
        "strict_output": strict_output,
        "use_kb_source": use_kb_source,
        "strict_output_source": strict_output_source,
        "citations": citations,
        "text_excerpt": (text or "")[:400] if text else None,
        # compat con vecchia struttura (thread/run) anche se qui usiamo Responses:
        "thread_id": None,
        "run_id": getattr(response, "id", None),
    }

    # Exit code:
    # 0 = ok, oppure KB opzionale / non richiesta
    # 4 = warning: KB non usata nonostante richiesta esplicita
    exit_code = 0
    if use_kb and not (out["used_file_search"] or citations):
        exit_code = 4

    _print_json(out, exit_code)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # pragma: no cover - diagnostico
        _print_json(
            {
                "status": "exception",
                "error": str(e),
                "traceback": traceback.format_exc(limit=5),
            },
            2,
        )
