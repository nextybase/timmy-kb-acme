# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.env_attestation import (
    REQUIRED_OPENAI_VERSION,
    ensure_env_attestation,
    validate_env_attestation,
    write_env_attestation,
)
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text


def _seed_requirements(repo_root: Path) -> None:
    safe_write_text(repo_root / "requirements.txt", "openai==2.3.0\n", encoding="utf-8", atomic=True)
    safe_write_text(repo_root / "requirements-dev.txt", "pytest==8.0.0\n", encoding="utf-8", atomic=True)


def test_write_and_validate_attestation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_requirements(tmp_path)
    monkeypatch.setattr(
        "pipeline.env_attestation._openai_runtime_probe",
        lambda: {
            "openai_version": REQUIRED_OPENAI_VERSION,
            "responses_create_signature": "(**kwargs)",
            "responses_create_supports_text": True,
        },
    )
    monkeypatch.setattr("pipeline.env_attestation.metadata.version", lambda name: REQUIRED_OPENAI_VERSION)

    path = write_env_attestation(repo_root=tmp_path, installed_by="tester")
    status = validate_env_attestation(repo_root=tmp_path)

    assert path.exists()
    assert status.ok is True
    assert status.errors == ()


def test_validate_attestation_detects_requirements_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_requirements(tmp_path)
    monkeypatch.setattr(
        "pipeline.env_attestation._openai_runtime_probe",
        lambda: {
            "openai_version": REQUIRED_OPENAI_VERSION,
            "responses_create_signature": "(**kwargs)",
            "responses_create_supports_text": True,
        },
    )
    monkeypatch.setattr("pipeline.env_attestation.metadata.version", lambda name: REQUIRED_OPENAI_VERSION)

    write_env_attestation(repo_root=tmp_path)
    safe_write_text(tmp_path / "requirements.txt", "openai==9.9.9\n", encoding="utf-8", atomic=True)

    status = validate_env_attestation(repo_root=tmp_path)
    assert status.ok is False
    assert any("requirements_hashes mismatch" in error for error in status.errors)


def test_ensure_attestation_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        ensure_env_attestation(repo_root=tmp_path)
    assert "Environment invalid - reinstall required." in str(exc.value)
