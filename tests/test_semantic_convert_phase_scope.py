# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConversionError
from pipeline.file_utils import safe_write_text
from semantic import convert_service
from tests.support.contexts import TestClientCtx


def _make_ctx(base_dir: Path, raw_dir: Path, book_dir: Path) -> TestClientCtx:
    return TestClientCtx(
        slug="dummy",
        repo_root_dir=base_dir,
        semantic_dir=base_dir / "semantic",
        config_dir=base_dir / "config",
    )


def _write_minimal_layout(base: Path) -> None:
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "normalized").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    (base / "book" / "README.md").write_text("# KB\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")


def test_convert_markdown_logs_done_once_on_success(tmp_path: Path, caplog, monkeypatch):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    normalized = base / "normalized"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)
    safe_write_text(normalized / "alpha.md", "# Alpha\n", encoding="utf-8", atomic=True)

    ctx = _make_ctx(base, raw, book)
    logger = logging.getLogger("test.convert")
    caplog.set_level(logging.INFO)

    out = convert_service.convert_markdown(ctx, logger, slug="x")

    # Un solo log "done" nei successi
    done = [r for r in caplog.records if r.msg == "semantic.convert_markdown.done"]
    assert len(done) == 1
    assert out and (book / "alpha.md").exists()


def test_convert_markdown_phase_failed_on_no_output(tmp_path: Path, caplog, monkeypatch):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    normalized = base / "normalized"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)
    safe_write_text(normalized / "empty.md", "\n", encoding="utf-8", atomic=True)

    ctx = _make_ctx(base, raw, book)
    logger = logging.getLogger("test.convert")
    caplog.set_level(logging.INFO)

    with pytest.raises(ConversionError):
        convert_service.convert_markdown(ctx, logger, slug="x")

    # Deve risultare un phase_failed (non completed)
    msgs = [r.msg for r in caplog.records]
    assert "phase_failed" in msgs
    assert "phase_completed" not in msgs
