# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import CapabilityUnavailableError, ConfigError
from pipeline.ingest import provider as ingest_module


def _dummy_context() -> SimpleNamespace:
    return SimpleNamespace(slug="dummy", redact_logs=False)


def test_drive_provider_requires_drive_utils(monkeypatch, tmp_path):
    ctx = _dummy_context()
    logger = logging.getLogger("test.drive")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)

    monkeypatch.setattr(ingest_module, "get_drive_service", None)
    monkeypatch.setattr(ingest_module, "download_drive_pdfs_to_local", None)
    monkeypatch.setattr(
        ingest_module,
        "get_client_config",
        lambda context: {"integrations": {"drive": {"raw_folder_id": "folder"}}},
    )

    provider = ingest_module.DriveIngestProvider()
    with pytest.raises(CapabilityUnavailableError) as exc:
        provider.ingest_raw(
            context=ctx,
            raw_dir=raw_dir,
            logger=logger,
            non_interactive=True,
        )
    assert "pip install .[drive]" in str(exc.value)


def test_local_provider_copies_files(tmp_path):
    ctx = _dummy_context()
    logger = logging.getLogger("test.local")
    raw_dir = tmp_path / "workspace" / "raw"
    src_dir = tmp_path / "source"
    src_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    pdf = src_dir / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%dummy")

    provider = ingest_module.LocalIngestProvider()
    copied = provider.ingest_raw(
        context=ctx,
        raw_dir=raw_dir,
        logger=logger,
        non_interactive=True,
        local_path=src_dir,
    )

    assert copied >= 1
    assert (raw_dir / "doc.pdf").exists()


def _setup_drive_fixtures(tmp_path: Path, monkeypatch):
    ctx = type("Ctx", (), {"slug": "drive", "redact_logs": False})()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        ingest_module,
        "get_client_config",
        lambda context: {"integrations": {"drive": {"raw_folder_id": "fid123"}}},
        raising=True,
    )
    monkeypatch.setattr(ingest_module, "get_drive_service", lambda _c: object(), raising=True)
    monkeypatch.setattr(
        ingest_module,
        "download_drive_pdfs_to_local",
        lambda **_: None,
        raising=True,
    )
    return ctx, raw_dir


def test_drive_provider_count_failure_strict(monkeypatch, tmp_path: Path):
    ctx, raw_dir = _setup_drive_fixtures(tmp_path, monkeypatch)
    provider = ingest_module.DriveIngestProvider()

    def _raising_iter(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest_module, "iter_safe_pdfs", _raising_iter, raising=True)
    monkeypatch.setattr(ingest_module, "is_beta_strict", lambda: True, raising=False)

    with pytest.raises(ConfigError) as exc:
        provider.ingest_raw(
            context=ctx,
            raw_dir=raw_dir,
            logger=logging.getLogger("test.drive"),
            non_interactive=True,
        )
    assert "Drive PDF count failed" in str(exc.value)


def test_drive_provider_count_failure_non_strict_logs(monkeypatch, tmp_path: Path, caplog):
    ctx, raw_dir = _setup_drive_fixtures(tmp_path, monkeypatch)
    provider = ingest_module.DriveIngestProvider()

    def _raising_iter(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest_module, "iter_safe_pdfs", _raising_iter, raising=True)
    monkeypatch.setattr(ingest_module, "is_beta_strict", lambda: False, raising=False)

    caplog.set_level(logging.WARNING)
    result = provider.ingest_raw(
        context=ctx,
        raw_dir=raw_dir,
        logger=logging.getLogger("test.drive"),
        non_interactive=True,
    )
    assert result is None
    record = next(r for r in caplog.records if r.msg == "ingest_provider.drive_count_failed")
    assert getattr(record, "service_only", None) is True
