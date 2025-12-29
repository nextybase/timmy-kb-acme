# SPDX-License-Identifier: GPL-3.0-only
"""Debug rapido per VisionOutput schema e response_format."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:

    import semantic.vision_provision as vp  # noqa: E402

    schema = vp._load_vision_schema()  # type: ignore[attr-defined]
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    if not isinstance(props, dict):
        raise SystemExit("properties non Ã¨ un oggetto nel JSON schema")
    if not isinstance(required, list):
        raise SystemExit("required non Ã¨ una lista nel JSON schema")

    props_keys = sorted(props.keys())
    required_keys = sorted(required)

    diff_required = [k for k in required_keys if k not in props_keys]
    diff_props = [k for k in props_keys if k not in required_keys]

    print("schema_path:", vp._vision_schema_path())  # type: ignore[attr-defined]
    print("module_path:", vp.__file__)
    print("properties:", props_keys)
    print("required:", required_keys)
    print("required_minus_properties:", diff_required)
    print("properties_minus_required:", diff_props)

    response_format = vp._build_response_format(use_structured=True)  # type: ignore[attr-defined]
    print("response_format_type:", response_format.get("type"))
    print("json_schema_name:", response_format.get("json_schema", {}).get("name"))
    print("strict:", response_format.get("json_schema", {}).get("strict"))
    response_schema = json.loads(json.dumps(response_format["json_schema"]["schema"]))
    print("response_schema_keys:", sorted(response_schema.get("properties", {}).keys()))


if __name__ == "__main__":
    main()
