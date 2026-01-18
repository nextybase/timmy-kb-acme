# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.paths import get_repo_root

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


def _debug_runtime_enabled() -> bool:
    raw = os.environ.get("DEBUG_RUNTIME") or os.environ.get("DEBUG") or ""
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _inspect_signature(create_fn: Any) -> tuple[Optional[str], Optional[bool], Optional[list[str]]]:
    try:
        signature_obj = inspect.signature(create_fn)
    except Exception:
        return None, None, None
    params = list(signature_obj.parameters.values())
    param_names = [param.name for param in params]
    supports_text = "text" in param_names or any(param.kind is inspect.Parameter.VAR_KEYWORD for param in params)
    return str(signature_obj), supports_text, param_names


def _runtime_info() -> tuple[str, str, str]:
    try:
        import openai  # type: ignore

        openai_version = getattr(openai, "__version__", "unknown")
        openai_file = getattr(openai, "__file__", "unknown")
    except Exception as exc:
        openai_version = f"unavailable:{type(exc).__name__}"
        openai_file = "unavailable"
    return sys.executable, openai_version, openai_file


def _dump_json_schema_payload(
    *,
    raw_response_format: Mapping[str, Any],
    normalized_format: Mapping[str, Any],
) -> None:
    if normalized_format.get("type") != "json_schema":
        return

    schema = normalized_format.get("schema")
    properties = []
    required = []
    if isinstance(schema, Mapping):
        props = schema.get("properties")
        reqs = schema.get("required")
        if isinstance(props, Mapping):
            properties = sorted(str(k) for k in props.keys())
        if isinstance(reqs, list):
            required = sorted(str(k) for k in reqs)

    payload = {
        "response_format_raw": raw_response_format,
        "text_format_normalized": normalized_format,
        "properties": properties,
        "required": required,
        "entity_to_area_in_properties": "entity_to_area" in properties,
        "entity_to_area_in_required": "entity_to_area" in required,
    }
    try:
        repo_root = get_repo_root(allow_env=False)
        dump_path = ensure_within_and_resolve(repo_root, repo_root / "output" / "debug" / "vision_schema_sent.json")
        dump_text = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        digest = hashlib.sha256(dump_text.encode("utf-8")).hexdigest()
        safe_write_text(dump_path, dump_text, encoding="utf-8")
        LOGGER.info(
            "ai.responses.json_schema_dumped",
            extra={"path": str(dump_path), "sha256": digest},
        )
    except Exception as exc:
        LOGGER.warning(
            "ai.responses.json_schema_dump_failed",
            extra={"error": str(exc)},
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


def _normalize_response_format(response_format: Dict[str, Any]) -> Dict[str, Any]:
    if response_format.get("type") != "json_schema":
        return response_format

    normalized = dict(response_format)
    schema_payload = response_format.get("json_schema")
    if isinstance(schema_payload, dict):
        normalized.pop("json_schema", None)
        for key in ("name", "schema", "strict", "description"):
            if key in schema_payload and key not in normalized:
                normalized[key] = schema_payload[key]

    if "name" not in normalized:
        raise ConfigError(
            "Responses text.format richiede name per json_schema.",
            code="responses.request.invalid",
            component="responses",
        )
    return normalized


def _diagnose_json_schema_format(rf_payload: Dict[str, Any]) -> Dict[str, Any]:
    schema = rf_payload.get("schema")
    if not isinstance(schema, Mapping):
        schema = {}

    properties = schema.get("properties")
    root_properties = sorted(properties.keys()) if isinstance(properties, Mapping) else []

    required = schema.get("required")
    root_required = sorted([str(item) for item in required]) if isinstance(required, list) else []

    required_minus_properties = [key for key in root_required if key not in root_properties]
    properties_minus_required = [key for key in root_properties if key not in root_required]

    has_pattern_properties_any = False
    has_one_of_any = False
    has_any_of_any = False
    has_all_of_any = False
    map_like_paths: List[str] = []

    stack: List[tuple[Mapping[str, Any], str]] = [(schema, "$")]
    while stack:
        node, path = stack.pop()

        if "patternProperties" in node:
            has_pattern_properties_any = True
        if "oneOf" in node:
            has_one_of_any = True
        if "anyOf" in node:
            has_any_of_any = True
        if "allOf" in node:
            has_all_of_any = True

        node_type = node.get("type")
        node_props = node.get("properties")
        node_additional = node.get("additionalProperties")
        if node_type == "object" and isinstance(node_additional, Mapping):
            if not (isinstance(node_props, Mapping) and node_props):
                map_like_paths.append(path)

        if isinstance(node_props, Mapping):
            for key in sorted(node_props.keys()):
                child = node_props.get(key)
                if isinstance(child, Mapping):
                    stack.append((child, f"{path}.{key}"))

        items = node.get("items")
        if isinstance(items, Mapping):
            stack.append((items, f"{path}[]"))
        elif isinstance(items, list):
            for idx, item in enumerate(items):
                if isinstance(item, Mapping):
                    stack.append((item, f"{path}[{idx}]"))

        if isinstance(node_additional, Mapping):
            stack.append((node_additional, f"{path}.*"))

        for branch_key in ("oneOf", "anyOf", "allOf"):
            branches = node.get(branch_key)
            if isinstance(branches, list):
                for idx, branch in enumerate(branches):
                    if isinstance(branch, Mapping):
                        stack.append((branch, f"{path}.{branch_key}[{idx}]"))

    map_like_paths_sorted = sorted(set(map_like_paths))[:30]
    fingerprint_source = json.dumps(
        {
            "properties": root_properties,
            "required": root_required,
            "map_like_paths": map_like_paths_sorted,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint_sha256 = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()

    return {
        "root_properties_count": len(root_properties),
        "root_required_count": len(root_required),
        "required_minus_properties": sorted(required_minus_properties)[:50],
        "properties_minus_required": sorted(properties_minus_required)[:50],
        "has_additionalProperties_root": "additionalProperties" in schema,
        "has_patternProperties_any": has_pattern_properties_any,
        "has_oneOf_any": has_one_of_any,
        "has_anyOf_any": has_any_of_any,
        "has_allOf_any": has_all_of_any,
        "map_like_paths": map_like_paths_sorted,
        "fingerprint_sha256": fingerprint_sha256,
    }


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
    # Paranoid guard: fail fast if Responses API is not available or callable.
    resp_api = getattr(client, "responses", None)
    create_fn = getattr(resp_api, "create", None) if resp_api is not None else None
    if not callable(create_fn):
        LOGGER.error(
            "ai.responses.unsupported",
            extra={"error": "responses.create missing_or_not_callable"},
        )
        raise ConfigError(
            "Client OpenAI non supporta l'API Responses.",
            code="responses.unsupported",
            component="responses",
        )
    input_payload = _to_input_blocks(messages)
    raw_response_format = response_format or {"type": "json_object"}
    rf_payload = _normalize_response_format(raw_response_format)
    if _debug_runtime_enabled():
        _dump_json_schema_payload(
            raw_response_format=raw_response_format,
            normalized_format=rf_payload,
        )
    if rf_payload.get("type") == "json_schema":
        raw_name = rf_payload.get("name")
        name = str(raw_name) if raw_name is not None else ""
        name_truncated = name[:80] if name else ""
        LOGGER.info(
            "ai.responses.json_schema_format",
            extra={
                "type": "json_schema",
                "name_present": bool(name_truncated),
                "format_name": name_truncated,
                "schema_present": "schema" in rf_payload,
                "json_schema_present": "json_schema" in rf_payload,
            },
        )
        diagnostics = _diagnose_json_schema_format(rf_payload)
        LOGGER.info(
            "ai.responses.json_schema_diagnostics",
            extra={
                **diagnostics,
                "schema_name": name_truncated,
                "name_present": bool(name_truncated),
            },
        )
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

    signature_text, supports_text, signature_params = _inspect_signature(create_fn)
    if _debug_runtime_enabled():
        sys_executable, openai_version, openai_file = _runtime_info()
        LOGGER.info(
            "ai.responses.signature",
            extra={
                "openai_version": openai_version,
                "openai_file": openai_file,
                "sys_executable": sys_executable,
                "signature": signature_text,
                "supports_text": supports_text,
            },
        )
    if not supports_text:
        params_value = ", ".join(signature_params or []) or "unavailable"
        message = (
            "SDK Responses.create non supporta text.format; parametri disponibili="
            f"{params_value}; upgrade richiesto."
        )
        if _debug_runtime_enabled():
            sys_executable, openai_version, openai_file = _runtime_info()
            signature_value = signature_text or "unavailable"
            message = (
                f"{message} Runtime: exe={sys_executable} openai={openai_version} "
                f"file={openai_file} signature={signature_value}"
            )
        raise ConfigError(
            message,
            code="responses.request.invalid",
            component="responses",
        )

    try:
        request_kwargs: Dict[str, Any] = {
            "model": model,
            "input": input_payload,
            "metadata": normalized_metadata,
            "text": {"format": rf_payload},
        }
        resp = client.responses.create(**request_kwargs)
    except TypeError as exc:
        LOGGER.error(
            "ai.responses.invalid_request",
            extra={"error": str(exc), "kwargs": sorted(request_kwargs.keys())},
        )
        raise ConfigError(
            f"Chiamata Responses fallita per incompatibilita' SDK/argomenti: {exc}",
            code="responses.request.invalid",
            component="responses",
        ) from exc
    except AttributeError as exc:  # pragma: no cover
        # Extra-paranoid: if the SDK raises AttributeError mid-flight, classify as unsupported.
        LOGGER.error("ai.responses.unsupported", extra={"error": str(exc)})
        raise ConfigError(
            "Client OpenAI non supporta l'API Responses.",
            code="responses.unsupported",
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
    return json.loads(payload)
