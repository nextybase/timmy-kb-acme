# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipeline.exceptions import QaGateViolation
from pipeline.qa_evidence import QA_EVIDENCE_FILENAME, load_qa_evidence, qa_evidence_path


@dataclass(frozen=True)
class QaGateResult:
    """Esito normalizzato del QA gate (solo campi normativi)."""

    schema_version: int
    qa_status: str
    checks_executed: list[str]


def _format_evidence_path(path: Path) -> str:
    name = path.name
    if name == QA_EVIDENCE_FILENAME:
        parent = path.parent.name
        if parent:
            return f"{parent}/{name}"
        return name
    return name


def _evidence_refs(path: Path, reason: str, qa_status: str | None = None) -> list[str]:
    safe_path = _format_evidence_path(path)
    refs = [
        f"qa_gate:{reason}",
        f"qa_path:{safe_path}",
    ]
    if qa_status:
        refs.append(f"qa_status:{qa_status}")
    return refs


def require_qa_gate_pass(log_dir: Path, *, slug: str | None = None) -> QaGateResult:
    """
    Gate QA deterministico: usa solo campi normativi (qa_status/checks_executed).

    Solleva QaGateViolation se:
    - evidence mancante/invalid
    - qa_status != pass
    """
    try:
        path = qa_evidence_path(log_dir)
    except Exception:
        path = Path(log_dir) / QA_EVIDENCE_FILENAME
    try:
        evidence = load_qa_evidence(log_dir)
    except Exception as exc:
        reason = getattr(exc, "code", None) or "qa_evidence_invalid"
        reason = "qa_evidence_missing" if reason == "qa_evidence_missing" else "qa_evidence_invalid"
        raise QaGateViolation(
            "QA gate failed.",
            slug=slug,
            file_path=path,
            reason=reason,
            evidence_refs=_evidence_refs(path, reason),
        ) from exc

    qa_status = str(evidence.get("qa_status") or "").strip().lower()
    if qa_status != "pass":
        raise QaGateViolation(
            "QA gate failed.",
            slug=slug,
            file_path=path,
            reason="qa_evidence_failed",
            evidence_refs=_evidence_refs(path, "qa_evidence_failed", qa_status=qa_status or None),
        )

    raw_checks = evidence.get("checks_executed")
    if not isinstance(raw_checks, list) or not all(isinstance(item, str) for item in raw_checks):
        raise QaGateViolation(
            "QA gate failed.",
            slug=slug,
            file_path=path,
            reason="qa_evidence_invalid",
            evidence_refs=_evidence_refs(path, "qa_evidence_invalid"),
        )

    return QaGateResult(
        schema_version=int(evidence.get("schema_version", 0)),
        qa_status=qa_status,
        checks_executed=list(raw_checks),
    )


__all__ = ["QaGateResult", "require_qa_gate_pass"]
