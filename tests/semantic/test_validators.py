# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from semantic.contracts import AssertionContract, RelationContract
from semantic.explain_pack import build_explain_pack
from semantic.validators import validate_explain_pack, validate_explanations, validate_kg


def _sample_assertions() -> list[AssertionContract]:
    return [
        {"assertion_id": "A1", "source": "proto", "relations": ["R1"]},
        {"assertion_id": "A2", "source": "proto", "relations": []},
    ]


def _sample_relations() -> list[RelationContract]:
    return [
        {
            "relation_id": "R1",
            "from_assertion": "A1",
            "to_assertion": "A2",
            "type": "supports",
            "provenance_ref": "run-x",
        }
    ]


def test_validate_kg_ok() -> None:
    errors = validate_kg(assertions=_sample_assertions(), relations=_sample_relations())
    assert errors == []


def test_validate_kg_missing_relation() -> None:
    bad_assertions = [
        {"assertion_id": "A1", "relations": ["R-unknown"]},
    ]
    errors = validate_kg(assertions=bad_assertions, relations=_sample_relations())
    assert errors


def test_validate_explanations_ok() -> None:
    assertions = _sample_assertions()
    explanations = [{"assertion_id": "A1"}]
    errors = validate_explanations(explanations=explanations, assertions=assertions)
    assert errors == []


def test_validate_explanations_missing_assertion() -> None:
    explanations = [{"assertion_id": "A-unknown"}]
    errors = validate_explanations(explanations=explanations, assertions=_sample_assertions())
    assert errors


def test_validate_explain_pack_structure() -> None:
    pack = build_explain_pack(
        assertions=_sample_assertions(),
        relations=_sample_relations(),
        explanations=[{"assertion_id": "A1"}],
        run_id="run-x",
        trace_id="trace-y",
    )
    errors = validate_explain_pack(pack=pack)
    assert errors == []


def test_validate_explain_pack_missing_keys() -> None:
    errors = validate_explain_pack(pack={})
    assert errors
