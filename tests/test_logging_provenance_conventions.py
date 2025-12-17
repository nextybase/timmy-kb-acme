# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging

from rosetta.client import OpenAIRosettaClient


def _build_rosetta_client():
    return OpenAIRosettaClient(slug="client-slug", client_factory=lambda: object())


def test_rosetta_logs_provenance_keys_and_masking(caplog):
    caplog.set_level(logging.INFO)
    client = _build_rosetta_client()

    with caplog.at_level(logging.INFO):
        client.check_coherence(
            assertions=[{"id": "a"}, {"id": "b"}],
            run_id="run-xyz",
            metadata={"ticket": "T1"},
        )

    record = caplog.records[-1]
    assert record.event == "rosetta.check_coherence"
    assert record.run_id == "run-xyz"
    assert record.slug == "client-slug"
    assert record.client_slug == "client-slug"
    assert record.assertions_count == 2
    assert record.metadata_fields_count == 1
    assert not hasattr(record, "candidate")
    assert not hasattr(record, "provenance")


def test_rosetta_logs_establish_conventions_for_propose(caplog):
    caplog.set_level(logging.INFO)
    client = _build_rosetta_client()

    with caplog.at_level(logging.INFO):
        client.propose_updates(
            assertion_id="assert-123",
            candidate={"field1": 1},
            provenance={"source": "test"},
            run_id="run-xyz",
        )

    record = caplog.records[-1]
    assert record.event == "rosetta.propose_updates"
    assert record.assertion_id == "assert-123"
    assert record.candidate_fields_count == 1
    assert record.provenance_fields_count == 1
    assert "candidate" not in record.__dict__
    assert "provenance" not in record.__dict__
