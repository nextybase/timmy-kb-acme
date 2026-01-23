# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from pipeline.exceptions import CapabilityUnavailableError
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
        lambda context: {"drive_raw_folder_id": "folder"},
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
