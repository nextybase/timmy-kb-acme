# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger

from .client_factory import make_openai_client
from .types import ResponseJson, ResponseText

LOGGER = get_structured_logger("ai.responses")

_INVOCATION_KEYS: Sequence[str] = (
    "component",
    "operation",
    "step",
    "assistant_id",
    "request_tag",
    "strict_output",
    "use_kb",
    "retention_days",
    "phase",
    "trace_id",
)


def _build_invocation_extra(
    *,
    invocation: Mapping[str, Any] | None,
    model: str,
    messages: int,
    response_format: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    extra: dict[str, Any] = {
        "event": "ai.invocation",
        "model": model,
        "messages": messages,
        "provider": "openai.responses",
    }
    if response_format:
        extra["response_format_type"] = response_format.get("type")
        schema_payload = response_format.get("json_schema")
        if isinstance(schema_payload, Mapping):
            name = schema_payload.get("name")
            if isinstance(name, str):
                extra["response_format_schema"] = name
            schema = schema_payload.get("schema")
            if isinstance(schema, Mapping):
                extra["response_format_keys"] = sorted(schema.keys())
    if invocation:
        for key in _INVOCATION_KEYS:
            value = invocation.get(key)
            if value is not None:
                extra[key] = value
    return extra


def _extract_output_text(response: Any) -> str:
    """
    Estrae il testo da una risposta OpenAI Responses, replicando il pattern usato nel repo.
    """
    # Alcune versioni dell'SDK espongono direttamente l'output aggregato.
    direct_text = getattr(response, "output_text", None)
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        raise ConfigError(
            "Risposta Responses non valida: attributo 'output' mancante o non-list.",
            code="responses.output.invalid",
            component="responses",
        )

    def _maybe_text_from_block(block: Any) -> str | None:
        if block is None:
            return None
        if getattr(block, "type", None) == "output_text":
            text_obj = getattr(block, "text", None)
            value = getattr(text_obj, "value", None) if text_obj is not None else None
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    for item in output:
        # Forma A: output=[OutputText(...)]
        direct = _maybe_text_from_block(item)
        if direct:
            return direct

        # Forma B (più comune): output=[Message(content=[OutputText(...), ...]), ...]
        if getattr(item, "type", None) == "message":
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for block in content:
                    nested = _maybe_text_from_block(block)
                    if nested:
                        return nested

    raise ConfigError("Responses completata ma nessun testo nel messaggio di output.")


def _mask_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not metadata:
        return {}
    # Masking leggero: logghiamo solo le chiavi e i tipi per evitare dati sensibili.
    return {key: type(val).__name__ for key, val in metadata.items()}


def _normalize_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Converte tutti i valori del metadata in stringa, come richiesto dalla Responses API.
    """
    if not metadata:
        return {}
    return {str(k): str(v) for k, v in metadata.items()}


def _to_input_blocks(messages: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    input_payload: List[Dict[str, Any]] = []
    for msg in messages:
        role = (msg.get("role") or "user").strip() if isinstance(msg, Mapping) else "user"
        content_raw = msg.get("content") if isinstance(msg, Mapping) else ""
        if isinstance(content_raw, list):
            content_block = content_raw
        else:
            content_block = [{"type": "input_text", "text": str(content_raw)}]
        input_payload.append(
            {
                "role": role or "user",
                "content": content_block,
            }
        )
    return input_payload


def run_text_model(
    model: str,
    messages: Iterable[Mapping[str, Any]],
    *,
    metadata: Optional[Mapping[str, Any]] = None,
    client: Any = None,
    invocation: Optional[Mapping[str, Any]] = None,
) -> ResponseText:
    """
    Esegue una chiamata Responses testuale (senza response_format).
    """
    client = client or make_openai_client()
    msg_list: List[Mapping[str, Any]] = list(messages)
    input_payload = _to_input_blocks(msg_list)
    normalized_metadata = _normalize_metadata(metadata)

    LOGGER.info(
        "ai.responses.text",
        extra={"model": model, "metadata": _mask_metadata(metadata), "messages": len(msg_list)},
    )
    LOGGER.info(
        "ai.invocation",
        extra=_build_invocation_extra(
            invocation=invocation,
            model=model,
            messages=len(msg_list),
            response_format=None,
        ),
    )

    try:
        resp = client.responses.create(
            model=model,
            input=input_payload,
            metadata=normalized_metadata,
        )
    except AttributeError as exc:  # pragma: no cover - client privo di responses
        LOGGER.error("ai.responses.unsupported", extra={"error": str(exc)})
        raise ConfigError("Client OpenAI non supporta l'API Responses.") from exc
    except Exception as exc:
        LOGGER.error("ai.responses.error", extra={"error": str(exc)})
        raise ConfigError(f"Chiamata Responses fallita: {exc}") from exc

    text = _extract_output_text(resp)
    return ResponseText(model=model, text=text, raw=resp)


def run_json_model(
    *,
    model: str,
    messages: List[Dict[str, str]],
    response_format: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    client: Any = None,
    invocation: Optional[Mapping[str, Any]] = None,
) -> ResponseJson:
    """
    Esegue una chiamata Responses con output JSON e valida il parsing.
    `messages` segue il formato chat role/content e viene convertito in input_text.
    """
    client = client or make_openai_client()
    input_payload = _to_input_blocks(messages)
    rf_payload = response_format or {"type": "json_object"}
    normalized_metadata = _normalize_metadata(metadata)

    LOGGER.info(
        "ai.responses.json",
        extra={
            "model": model,
            "metadata": _mask_metadata(metadata),
            "messages": len(messages),
            "response_format_keys": sorted(rf_payload.keys()),
        },
    )
    LOGGER.info(
        "ai.invocation",
        extra=_build_invocation_extra(
            invocation=invocation,
            model=model,
            messages=len(messages),
            response_format=rf_payload,
        ),
    )

    try:
        resp = client.responses.create(
            model=model,
            input=input_payload,
            metadata=normalized_metadata,
            response_format=rf_payload,
        )
    except AttributeError as exc:  # pragma: no cover
        LOGGER.error("ai.responses.unsupported", extra={"error": str(exc)})
        raise ConfigError("Client OpenAI non supporta l'API Responses.") from exc
    except TypeError as exc:
        # Alcune versioni dell'SDK non accettano `response_format` su Responses.create.
        # In tal caso riproviamo senza `response_format`, mantenendo comunque il vincolo
        # "JSON-only" a livello di prompt/system message.
        if "response_format" in str(exc):
            try:
                resp = client.responses.create(
                    model=model,
                    input=input_payload,
                    metadata=normalized_metadata,
                )
            except Exception as inner_exc:  # pragma: no cover - fallback best-effort
                raise ConfigError(
                    f"Chiamata Responses fallita per incompatibilità SDK/argomenti: {exc}",
                    code="responses.request.invalid",
                    component="responses",
                ) from inner_exc
        else:
            raise ConfigError(
                f"Chiamata Responses fallita per incompatibilità SDK/argomenti: {exc}",
                code="responses.request.invalid",
                component="responses",
            ) from exc
    except Exception as exc:
        LOGGER.error("ai.responses.error", extra={"error": str(exc)})
        raise ConfigError(f"Chiamata Responses fallita: {exc}") from exc

    status = getattr(resp, "status", None)
    if status and status != "completed":
        LOGGER.error(
            "ai.responses.failed",
            extra={"status": status, "id": getattr(resp, "id", None)},
        )
        raise ConfigError(f"Responses run non completato (status={status}).")

    text = _extract_output_text(resp)

    try:
        data = _parse_json_payload(text)
    except Exception as exc:
        LOGGER.error("ai.responses.invalid_json", extra={"error": str(exc), "sample": text[:500]})
        raise ConfigError(f"Risposta modello non JSON valido: {exc}") from exc

    return ResponseJson(model=model, data=data, raw_text=text, raw=resp)


def _parse_json_payload(payload: str) -> Dict[str, Any]:
    def _strip_fences(candidate: str) -> str:
        stripped = candidate.strip()
        if stripped.startswith("```") and stripped.count("```") >= 2:
            parts = stripped.split("```")
            stripped = parts[1] if len(parts) > 1 else stripped
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].lstrip()
        return stripped.strip()

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        if "```" in payload:
            for chunk in payload.split("```"):
                chunk = _strip_fences(chunk)
                if not chunk:
                    continue
                try:
                    return json.loads(chunk)
                except Exception:
                    continue
        raise
