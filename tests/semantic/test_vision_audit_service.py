# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from semantic import vision_provision as vp


def test_vision_audit_line_failure_logs_service_event(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Questo test verifica logging service-only: in strict state fallisce prima con ConfigError.
    monkeypatch.setattr(vp, "is_beta_strict", lambda: False, raising=False)
    repo_root = tmp_path / "workspace"
    repo_root.mkdir()
    record = {"slug": "test-slug", "ts": "ts-value"}

    def _failing_append(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit append failed")

    monkeypatch.setattr(vp, "safe_append_text", _failing_append)
    caplog.set_level(logging.WARNING)

    vp._write_audit_line(repo_root, record)

    service_records = [rec for rec in caplog.records if rec.message == vp._evt("audit_write_failed")]
    assert len(service_records) == 1
    rec = service_records[0]
    assert rec.slug == "test-slug"
    assert rec.scene == "service"
    assert rec.service_only is True
    assert rec.operation == "audit_append"
    assert rec.service == "semantic.vision.audit_log"
    assert rec.error_type == "RuntimeError"
    assert "audit append failed" in rec.reason
    assert str(repo_root / "logs" / vp.LOG_FILE_NAME) == rec.path


def test_vision_audit_lock_cleanup_failure_logs_service_event(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "workspace"
    repo_root.mkdir()
    record = {"slug": "lock-slug", "ts": "ts-value"}

    def _write_with_stale_lock(
        root_dir: Path,
        log_path: Path,
        payload: str,
        *,
        encoding: str = "utf-8",
        lock_timeout: float = 5.0,
        fsync: bool = False,
    ) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(payload, encoding=encoding)
        lock_path = log_path.parent / f"{log_path.name}.lock"
        lock_path.write_text("locked", encoding="utf-8")

    monkeypatch.setattr(vp, "safe_append_text", _write_with_stale_lock)
    caplog.set_level(logging.WARNING)

    vp._write_audit_line(repo_root, record)

    service_records = [rec for rec in caplog.records if rec.message == vp._evt("audit_lock_cleanup_failed")]
    assert len(service_records) == 1
    rec = service_records[0]
    assert rec.slug == "lock-slug"
    assert rec.scene == "service"
    assert rec.service_only is True
    assert rec.operation == "lock_cleanup"
    assert rec.service == "semantic.vision.audit_log"
    assert rec.reason == "lock_stale"
    assert rec.lock_path.endswith(".lock")
