# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

QA_EVIDENCE_FILENAME = "qa_passed.json"
QA_SCHEMA_VERSION = 1
QA_STATUS_VALUES = {"pass", "fail"}

__all__ = [
    "QA_EVIDENCE_FILENAME",
    "QA_SCHEMA_VERSION",
    "build_qa_evidence_payload",
    "load_qa_evidence",
    "qa_evidence_path",
    "validate_qa_evidence_payload",
    "write_qa_evidence",
]


def qa_evidence_path(log_dir: Path) -> Path:
    """Return the canonical path for the QA evidence file inside log_dir."""
    return Path(ensure_within_and_resolve(log_dir, log_dir / QA_EVIDENCE_FILENAME))


def build_qa_evidence_payload(
    *,
    checks_executed: Sequence[str],
    qa_status: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build the minimal QA evidence payload."""
    normalized_checks = [str(item).strip() for item in (checks_executed or []) if str(item).strip()]
    if not normalized_checks:
        raise ConfigError("checks_executed is required for QA evidence.", code="qa_evidence_invalid")
    status = str(qa_status or "").strip().lower()
    if status not in QA_STATUS_VALUES:
        raise ConfigError("qa_status must be 'pass' or 'fail'.", code="qa_evidence_invalid")
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    if not isinstance(ts, str) or not ts.strip():
        raise ConfigError("timestamp is required for QA evidence.", code="qa_evidence_invalid")
    return {
        "schema_version": QA_SCHEMA_VERSION,
        "qa_status": status,
        "checks_executed": normalized_checks,
        "timestamp": ts,
    }


def validate_qa_evidence_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate QA evidence payload and return a normalized dict."""
    if not isinstance(payload, Mapping):
        raise ConfigError("QA evidence must be a JSON object.", code="qa_evidence_invalid")

    schema_version = payload.get("schema_version")
    if schema_version != QA_SCHEMA_VERSION:
        raise ConfigError("QA evidence schema_version mismatch.", code="qa_evidence_invalid")

    qa_status = str(payload.get("qa_status") or "").strip().lower()
    if qa_status not in QA_STATUS_VALUES:
        raise ConfigError("QA evidence qa_status invalid.", code="qa_evidence_invalid")

    checks_raw = payload.get("checks_executed")
    if not isinstance(checks_raw, list):
        raise ConfigError("QA evidence checks_executed must be a list.", code="qa_evidence_invalid")
    checks = [str(item).strip() for item in checks_raw if str(item).strip()]
    if not checks:
        raise ConfigError("QA evidence checks_executed cannot be empty.", code="qa_evidence_invalid")

    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ConfigError("QA evidence timestamp invalid.", code="qa_evidence_invalid")

    return {
        "schema_version": QA_SCHEMA_VERSION,
        "qa_status": qa_status,
        "checks_executed": checks,
        "timestamp": timestamp,
    }


def load_qa_evidence(log_dir: Path) -> dict[str, Any]:
    """Load and validate QA evidence from log_dir."""
    path = qa_evidence_path(log_dir)
    if not path.exists():
        raise ConfigError("QA evidence missing.", code="qa_evidence_missing", file_path=path)
    try:
        raw = read_text_safe(log_dir, path, encoding="utf-8")
        data = json.loads(raw or "")
    except Exception as exc:
        raise ConfigError(
            "QA evidence unreadable or invalid JSON.",
            code="qa_evidence_invalid",
            file_path=path,
        ) from exc
    return validate_qa_evidence_payload(data)


def write_qa_evidence(
    log_dir: Path,
    *,
    checks_executed: Sequence[str],
    qa_status: str,
    timestamp: str | None = None,
    logger: logging.Logger | None = None,
) -> Path:
    """Write QA evidence to log_dir (fails loudly on errors)."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        payload = build_qa_evidence_payload(
            checks_executed=checks_executed,
            qa_status=qa_status,
            timestamp=timestamp,
        )
        path = qa_evidence_path(log_dir)
        safe_write_text(path, json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        if logger:
            logger.info("qa_evidence.written", extra={"path": str(path), "qa_status": payload["qa_status"]})
        return path
    except (ConfigError, PipelineError):
        raise
    except Exception as exc:
        raise PipelineError("Unable to write QA evidence.", code="qa_evidence_write_failed") from exc
