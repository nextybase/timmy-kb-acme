# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json

from semantic.contracts import AssertionContract, RelationContract
from semantic.exporters import export_kg_json, export_kg_markdown


def test_export_json_serializzabile() -> None:
    assertions: list[AssertionContract] = [
        {"assertion_id": "A1", "source": "proto", "confidence": 0.9, "relations": ["R1"]},
    ]
    relations: list[RelationContract] = [
        {
            "relation_id": "R1",
            "from_assertion": "A1",
            "to_assertion": "A2",
            "type": "supports",
            "provenance_ref": "run-42",
        },
    ]
    payload = export_kg_json(
        assertions=assertions,
        relations=relations,
        explanations={"summary": "stub"},
        run_id="run-42",
    )
    # deve essere serializzabile JSON
    json.dumps(payload)
    assert payload["metadata"]["run_id"] == "run-42"


def test_export_markdown_contains_sections() -> None:
    assertions: list[AssertionContract] = [
        {"assertion_id": "A1", "source": "proto", "relations": []},
    ]
    relations: list[RelationContract] = [
        {
            "relation_id": "R1",
            "from_assertion": "A1",
            "to_assertion": "A2",
            "type": "supports",
            "provenance_ref": "run-42",
        },
    ]
    markdown = export_kg_markdown(
        assertions=assertions,
        relations=relations,
        explanations={"summary": "stub"},
    )
    assert "## Assertions" in markdown
    assert "## Relations" in markdown
    assert "## Explanations" in markdown
