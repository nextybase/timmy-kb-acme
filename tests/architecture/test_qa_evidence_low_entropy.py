# SPDX-License-Identifier: GPL-3.0-only
"""QA evidence: parte normativa deterministica e telemetria non vincolante."""

from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError
from pipeline.qa_evidence import build_qa_evidence_payload, validate_qa_evidence_payload


def _normative(payload: dict) -> dict:
    return {
        "schema_version": payload.get("schema_version"),
        "qa_status": payload.get("qa_status"),
        "checks_executed": payload.get("checks_executed"),
    }


def test_normative_payload_is_deterministic_across_timestamps() -> None:
    payload_a = build_qa_evidence_payload(
        checks_executed=["pre-commit run --all-files", "pytest -q"],
        qa_status="pass",
        timestamp="2025-01-01T00:00:00Z",
    )
    payload_b = build_qa_evidence_payload(
        checks_executed=["pre-commit run --all-files", "pytest -q"],
        qa_status="pass",
        timestamp="2025-02-01T00:00:00Z",
    )
    assert _normative(payload_a) == _normative(payload_b)


def test_validator_accepts_missing_or_telemetry_timestamp() -> None:
    minimal = {
        "schema_version": 1,
        "qa_status": "pass",
        "checks_executed": ["pytest -q"],
    }
    normalized_min = validate_qa_evidence_payload(minimal)
    assert _normative(normalized_min) == _normative(minimal)
    assert normalized_min.get("telemetry") == {}

    telemetry_payload = {
        "schema_version": 1,
        "qa_status": "pass",
        "checks_executed": ["pytest -q"],
        "telemetry": {"timestamp": "2025-01-01T00:00:00Z"},
    }
    normalized_telemetry = validate_qa_evidence_payload(telemetry_payload)
    assert _normative(normalized_telemetry) == _normative(telemetry_payload)
    assert normalized_telemetry.get("telemetry", {}).get("timestamp") == "2025-01-01T00:00:00Z"


def test_validator_rejects_legacy_top_level_timestamp() -> None:
    legacy = {
        "schema_version": 1,
        "qa_status": "pass",
        "checks_executed": ["pytest -q"],
        "timestamp": "2025-01-01T00:00:00Z",
    }
    with pytest.raises(ConfigError, match="Legacy field 'timestamp' at top-level is not allowed"):
        validate_qa_evidence_payload(legacy)
