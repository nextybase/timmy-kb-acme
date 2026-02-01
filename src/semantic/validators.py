# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Iterable, Mapping

from semantic.contracts import AssertionContract, RelationContract


def validate_kg(
    *,
    assertions: Iterable[AssertionContract],
    relations: Iterable[RelationContract],
) -> list[str]:
    assertion_ids = {assertion["assertion_id"] for assertion in assertions if "assertion_id" in assertion}
    relation_ids = {relation["relation_id"] for relation in relations}
    errors: list[str] = []
    for relation in relations:
        if relation["from_assertion"] not in assertion_ids:
            errors.append(f"from_assertion missing: {relation['relation_id']}")
        if relation["to_assertion"] not in assertion_ids:
            errors.append(f"to_assertion missing: {relation['relation_id']}")
    for assertion in assertions:
        for rel in assertion.get("relations", []):
            if rel not in relation_ids:
                errors.append(f"relation missing: {rel} in assertion {assertion.get('assertion_id')}")
    return errors


def validate_explanations(
    *,
    explanations: Iterable[Mapping[str, Any]],
    assertions: Iterable[AssertionContract],
) -> list[str]:
    assertion_ids = {assertion["assertion_id"] for assertion in assertions if "assertion_id" in assertion}
    errors: list[str] = []
    for explanation in explanations:
        assertion_id = explanation.get("assertion_id")
        if assertion_id and assertion_id not in assertion_ids:
            errors.append(f"explanation references unknown assertion: {assertion_id}")
    return errors


def validate_explain_pack(
    *,
    pack: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if "manifest" not in pack:
        errors.append("missing manifest")
    if "kg" not in pack:
        errors.append("missing kg payload")
    if "explanations" not in pack:
        errors.append("missing explanations")
    checksums = pack.get("checksums", {})
    if "kg" not in checksums or "explanations" not in checksums:
        errors.append("checksums incomplete")
    return errors
