# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Dict

from pipeline.exceptions import ConfigError

from .assistant_registry import resolve_kgraph_config
from .responses import run_json_model


def invoke_kgraph_messages(
    messages: list[dict[str, Any]],
    *,
    settings: Any | None = None,
    assistant_env: str | None = None,
    redact_logs: bool = False,
) -> Dict[str, Any]:
    """
    Esegue il modello KGraph via Responses API (model-only) e restituisce il JSON parsato.

    Args:
        messages: lista di messaggi già in formato Responses (input_text).
        settings: Settings o mapping configurazione, usato per risolvere modello/assistant.
        assistant_env: override del nome variabile d'ambiente per l'assistant.
        redact_logs: flag passato ai metadata per logging/telemetria.
    """
    if settings is None:
        raise ConfigError(
            "KGraph invocation requires explicit settings.",
            code="kgraph.settings.missing",
        )
    cfg = resolve_kgraph_config(settings, assistant_env_override=assistant_env)

    metadata: Dict[str, Any] = {
        "source": "kgraph",
        "assistant_id": cfg.assistant_id,
        "redact_logs": redact_logs,
    }

    try:
        resp = run_json_model(
            model=cfg.model,
            messages=messages,
            response_format=None,
            metadata=metadata,
            invocation={
                "component": "kgraph",
                "operation": "kgraph.invoke",
                "assistant_id": cfg.assistant_id,
                "request_tag": "kgraph.invoke",
            },
        )
    except ConfigError:
        raise
    except Exception as exc:  # pragma: no cover - protezione extra
        raise ConfigError(f"Responses API fallita per assistant {cfg.assistant_id}.") from exc

    return resp.data
