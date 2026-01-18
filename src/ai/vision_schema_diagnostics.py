# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

from .responses import _diagnose_json_schema_format

LOGGER = get_structured_logger("ai.vision.schema_diagnostics")


def _vision_schema_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    schema_path = repo_root / "src" / "ai" / "schemas" / "VisionOutput.schema.json"
    safe_path = ensure_within_and_resolve(repo_root, schema_path)
    if not Path(safe_path).exists():
        raise ConfigError(f"Vision schema non trovato in {safe_path}")
    return Path(safe_path)


def _load_vision_schema() -> Dict[str, Any]:
    schema_path = _vision_schema_path()
    raw = read_text_safe(schema_path.parents[0], schema_path, encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Vision schema JSON non valido: {exc}") from exc


def build_vision_schema_diagnostics() -> Dict[str, Any]:
    schema = _load_vision_schema()
    rf_payload = {"type": "json_schema", "schema": schema}
    return _diagnose_json_schema_format(rf_payload)


def main() -> None:
    diagnostics = build_vision_schema_diagnostics()
    LOGGER.info("ai.vision.schema_diagnostics", extra=diagnostics)
    print(json.dumps(diagnostics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
