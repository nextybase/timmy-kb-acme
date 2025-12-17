# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import Iterable, Mapping, Optional

from rosetta.client import RosettaClient
from semantic.contracts import AssertionContract, RelationContract


def test_kg_contract_types_importable() -> None:
    assertion: AssertionContract = {
        "assertion_id": "A-1",
        "source": "prototimmy",
        "confidence": 0.8,
        "relations": ["R-1"],
    }
    relation: RelationContract = {
        "relation_id": "R-1",
        "from_assertion": "A-1",
        "to_assertion": "A-2",
        "type": "supports",
        "provenance_ref": "run-42",
    }
    assert assertion["assertion_id"] == "A-1"
    assert relation["relation_id"] == "R-1"


def test_rosetta_client_accepts_assertion_contract() -> None:
    events: list[str] = []

    class DummyClient(RosettaClient):
        def check_coherence(
            self,
            *,
            assertions: Iterable[AssertionContract],
            run_id: Optional[str] = None,
            metadata: Optional[Mapping[str, object]] = None,
        ) -> Mapping[str, object]:
            events.append("check")
            assert all("assertion_id" in assertion for assertion in assertions)
            assert run_id == "run-kg"
            return {"status": "ok"}

        def propose_updates(
            self,
            *,
            assertion_id: str,
            candidate: Mapping[str, object],
            provenance: Optional[Mapping[str, object]] = None,
            run_id: Optional[str] = None,
        ) -> Mapping[str, object]:
            events.append("propose")
            return {"decision": "keep"}

        def explain(
            self,
            *,
            assertion_id: Optional[str] = None,
            trace_id: Optional[str] = None,
            run_id: Optional[str] = None,
            relations: Optional[Iterable[RelationContract]] = None,
            metadata: Optional[Mapping[str, object]] = None,
        ) -> Mapping[str, object]:
            events.append("explain")
            assert relations is not None
            return {"assertion_id": assertion_id, "trace_id": trace_id}

    client = DummyClient(slug="pt", model="stub")
    client.check_coherence(
        assertions=[
            {"assertion_id": "A-1", "source": "proto", "relations": []},
        ],
        run_id="run-kg",
    )
    client.explain(
        assertion_id="A-1",
        trace_id="trace-1",
        run_id="run-kg",
        relations=[
            {
                "relation_id": "R-1",
                "from_assertion": "A-1",
                "to_assertion": "A-2",
                "type": "supports",
                "provenance_ref": "run-kg",
            }
        ],
    )
    assert "check" in events and "explain" in events
