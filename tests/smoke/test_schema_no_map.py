# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

from ai import responses
from ai.vision_config import resolve_vision_config
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.paths import get_repo_root


def _load_schema(schema_path: Path) -> Dict[str, Any]:
    raw = schema_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Schema JSON non e' un oggetto.")
    return data


def _remove_map_like(schema: Dict[str, Any]) -> Dict[str, Any]:
    props = schema.get("properties")
    if isinstance(props, dict):
        props.pop("entity_to_area", None)
        props.pop("entity_to_document_type", None)
        schema["properties"] = props
    required_items = schema.get("required")
    if isinstance(required_items, list):
        schema["required"] = [
            item for item in required_items if item not in {"entity_to_area", "entity_to_document_type"}
        ]
    return schema


def _dump_payload(
    *,
    dump_path: Path,
    response_format_raw: Mapping[str, Any],
    text_format_normalized: Mapping[str, Any],
) -> str:
    schema = text_format_normalized.get("schema")
    properties = []
    required = []
    if isinstance(schema, Mapping):
        props = schema.get("properties")
        required_items = schema.get("required")
        if isinstance(props, Mapping):
            properties = sorted(str(k) for k in props.keys())
        if isinstance(required_items, list):
            required = sorted(str(k) for k in required_items)
    payload = {
        "response_format_raw": response_format_raw,
        "text_format_normalized": text_format_normalized,
        "properties": properties,
        "required": required,
        "entity_to_area_in_properties": "entity_to_area" in properties,
        "entity_to_area_in_required": "entity_to_area" in required,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    safe_write_text(dump_path, text, encoding="utf-8")
    return digest


def main() -> int:
    repo_root = get_repo_root(allow_env=False)
    artifacts_dir = ensure_within_and_resolve(repo_root, repo_root / "tests" / "artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    log_path = ensure_within_and_resolve(artifacts_dir, artifacts_dir / "test_schema_no_map.log")
    dump_path = ensure_within_and_resolve(artifacts_dir, artifacts_dir / "schema_no_map_sent.json")

    logger = get_structured_logger("tools.smoke.schema_no_map", log_file=log_path, propagate=True)
    logger.setLevel("INFO")

    try:
        import openai  # type: ignore

        openai_version = getattr(openai, "__version__", "unknown")
    except Exception:
        openai_version = "unavailable"

    logger.info("schema_test.env", extra={"python": sys.version.split()[0], "openai": openai_version})

    schema_path = ensure_within_and_resolve(
        repo_root, repo_root / "src" / "ai" / "schemas" / "VisionOutput.schema.json"
    )
    schema = _load_schema(schema_path)
    schema = _remove_map_like(schema)

    response_format_raw = {
        "type": "json_schema",
        "json_schema": {"name": "VisionOutput_v2", "schema": schema, "strict": True},
    }
    text_format = responses._normalize_response_format(dict(response_format_raw))
    digest = _dump_payload(
        dump_path=dump_path,
        response_format_raw=response_format_raw,
        text_format_normalized=text_format,
    )
    logger.info("schema_test.dumped", extra={"path": str(dump_path), "sha256": digest})

    ctx = ClientContext.load(slug="dummy", require_drive_env=False, run_id=None)
    resolved = resolve_vision_config(ctx)
    model = resolved.model

    messages = [{"role": "user", "content": "Return a valid JSON object matching the schema."}]
    try:
        responses.run_json_model(model=model, messages=messages, response_format=response_format_raw)
        logger.info("schema_test.result PASS")
        return 0
    except ConfigError as exc:
        logger.error("schema_test.result FAIL")
        logger.error("schema_test.error %s", exc)
        return 1
    except Exception as exc:
        logger.error("schema_test.result FAIL")
        logger.error("schema_test.error %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
