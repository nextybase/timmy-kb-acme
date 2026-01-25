# SPDX-License-Identifier: GPL-3.0-only
"""QA gate: determinism + low entropy sui core outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline.artifact_policy import enforce_core_artifacts
from pipeline.exceptions import ArtifactPolicyViolation, QaGateViolation
from pipeline.qa_evidence import QA_EVIDENCE_FILENAME
from pipeline.workspace_bootstrap import bootstrap_dummy_workspace
from storage import decision_ledger
from timmy_kb.cli import pre_onboarding, semantic_onboarding, tag_onboarding


def _bootstrap_dummy_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TIMMY_KB_DUMMY_OUTPUT_ROOT", str(tmp_path))
    layout = bootstrap_dummy_workspace("dummy")
    conn = decision_ledger.open_ledger(layout)
    conn.close()
    return layout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_expected_core_outputs_pre_onboarding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = _bootstrap_dummy_layout(tmp_path, monkeypatch)
    enforce_core_artifacts("pre_onboarding", layout=layout)


def test_core_downgrade_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = _bootstrap_dummy_layout(tmp_path, monkeypatch)
    readme_md = layout.book_dir / "README.md"
    readme_txt = layout.book_dir / "README.txt"
    if readme_md.exists():
        readme_md.unlink()
    readme_txt.write_text("downgraded", encoding="utf-8")

    with pytest.raises(ArtifactPolicyViolation) as exc:
        enforce_core_artifacts("pre_onboarding", layout=layout)

    assert any("missing" in ref for ref in exc.value.evidence_refs)


def test_stop_code_for_artifact_policy_violation() -> None:
    exc = ArtifactPolicyViolation("violation", slug="dummy")
    verdict, code = pre_onboarding._normative_verdict_for_error(exc)  # type: ignore[attr-defined]
    assert verdict == decision_ledger.NORMATIVE_BLOCK
    assert code == decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION

    verdict, code = tag_onboarding._normative_verdict_for_error(exc)  # type: ignore[attr-defined]
    assert verdict == decision_ledger.NORMATIVE_BLOCK
    assert code == decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION

    verdict, code = semantic_onboarding._normative_verdict_for_error(exc)  # type: ignore[attr-defined]
    assert verdict == decision_ledger.NORMATIVE_BLOCK
    assert code == decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION


def test_golden_manifest_matches_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = _bootstrap_dummy_layout(tmp_path, monkeypatch)
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "determinism_manifest.json"
    expected = json.loads(fixture_path.read_text(encoding="utf-8"))

    artifacts = []
    for rel, path in sorted(
        {
            "config/config.yaml": layout.config_path,
            "book/README.md": layout.book_dir / "README.md",
            "book/SUMMARY.md": layout.book_dir / "SUMMARY.md",
        }.items()
    ):
        artifacts.append({"path": rel, "sha256": _sha256(path), "bytes": path.stat().st_size})

    manifest = {"schema_version": 1, "artifacts": artifacts}
    assert manifest == expected


def _write_qa_evidence(log_dir: Path, *, qa_status: str) -> None:
    payload = {
        "schema_version": 1,
        "qa_status": qa_status,
        "checks_executed": ["pre-commit run --all-files", "pytest -q"],
    }
    (log_dir / QA_EVIDENCE_FILENAME).write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_semantic_onboarding_requires_qa_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = _bootstrap_dummy_layout(tmp_path, monkeypatch)
    (layout.book_dir / "content.md").write_text("# Content\n", encoding="utf-8")
    with pytest.raises(QaGateViolation) as exc:
        enforce_core_artifacts("semantic_onboarding", layout=layout)
    assert any("qa_gate" in ref for ref in exc.value.evidence_refs)


def test_semantic_onboarding_blocks_on_qa_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = _bootstrap_dummy_layout(tmp_path, monkeypatch)
    (layout.book_dir / "content.md").write_text("# Content\n", encoding="utf-8")
    _write_qa_evidence(layout.logs_dir, qa_status="fail")
    with pytest.raises(QaGateViolation) as exc:
        enforce_core_artifacts("semantic_onboarding", layout=layout)
    assert any("qa_evidence_failed" in ref for ref in exc.value.evidence_refs)
