# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConversionError
from semantic import api as sapi
from semantic import convert_service
from tests.support.contexts import TestClientCtx


def _make_ctx(base_dir: Path, raw_dir: Path, md_dir: Path) -> TestClientCtx:
    return TestClientCtx(slug="dummy", base_dir=base_dir, raw_dir=raw_dir, md_dir=md_dir)


def test_convert_markdown_logs_done_once_on_success(tmp_path: Path, caplog, monkeypatch):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    # Un PDF valido (contenuto irrilevante)
    (raw / "a.pdf").write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    # Falsa conversione: scrive un file di contenuto in book/
    def _fake_convert(ctx, *, md_dir=None, safe_pdfs=None):  # noqa: ANN001
        target_dir = Path(md_dir or ctx.md_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "alpha.md").write_text("# Alpha\n", encoding="utf-8")

    monkeypatch.setattr(convert_service, "_convert_md", _fake_convert, raising=True)

    ctx = _make_ctx(base, raw, book)
    logger = logging.getLogger("test.convert")
    caplog.set_level(logging.INFO)

    out = sapi.convert_markdown(ctx, logger, slug="x")

    # Un solo log "done" nei successi
    done = [r for r in caplog.records if r.msg == "semantic.convert_markdown.done"]
    assert len(done) == 1
    assert out and (book / "alpha.md").exists()


def test_convert_markdown_phase_failed_on_no_output(tmp_path: Path, caplog, monkeypatch):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    # Un PDF sicuro ma la conversione non produce contenuti
    (raw / "b.pdf").write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    def _noop_convert(ctx, *, md_dir=None, safe_pdfs=None):  # noqa: ANN001
        return None

    monkeypatch.setattr(convert_service, "_convert_md", _noop_convert, raising=True)

    ctx = _make_ctx(base, raw, book)
    logger = logging.getLogger("test.convert")
    caplog.set_level(logging.INFO)

    with pytest.raises(ConversionError):
        sapi.convert_markdown(ctx, logger, slug="x")

    # Deve risultare un phase_failed (non completed)
    msgs = [r.msg for r in caplog.records]
    assert "phase_failed" in msgs
    assert "phase_completed" not in msgs
