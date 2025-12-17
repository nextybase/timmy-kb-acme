# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json

from semantic.contracts import AssertionContract, RelationContract
from semantic.explain_pack import build_explain_pack


def test_explain_pack_serializzabile_e_checksum_coerenti() -> None:
    assertions: list[AssertionContract] = [
        {"assertion_id": "A1", "source": "proto", "relations": ["R1"]},
    ]
    relations: list[RelationContract] = [
        {
            "relation_id": "R1",
            "from_assertion": "A1",
            "to_assertion": "A2",
            "type": "supports",
            "provenance_ref": "run-x",
        }
    ]
    explanations = [{"assertion_id": "A1", "text": "stub"}]
    pack = build_explain_pack(
        assertions=assertions,
        relations=relations,
        explanations=explanations,
        run_id="run-x",
        trace_id="trace-y",
    )
    json.dumps(pack)
    checksums = pack["checksums"]
    assert checksums["kg"] == pack["checksums"]["kg"]
    assert "manifest" in pack
    assert pack["manifest"]["run_id"] == "run-x"
    assert pack["manifest"]["trace_id"] == "trace-y"
