# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_semantic_api_summary_readme.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from pipeline.exceptions import ConversionError
from pipeline.qa_evidence import QA_EVIDENCE_FILENAME
from semantic import frontmatter_service as front


@dataclass
class DummyCtx:
    repo_root_dir: Path
    base_dir: Path
    raw_dir: Path
    book_dir: Path
    slug: str = "e2e"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_minimal_layout(base: Path) -> None:
    _write(base / "config" / "config.yaml", "meta:\n  client_name: test\n")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "normalized").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    _write(base / "book" / "README.md", "# KB\n")
    _write(base / "book" / "SUMMARY.md", "# Summary\n")
    _write(base / "semantic" / "semantic_mapping.yaml", "{}")
    (base / "logs" / QA_EVIDENCE_FILENAME).write_text(
        '{"schema_version":1,"qa_status":"pass","checks_executed":["pytest -q"]}\n',
        encoding="utf-8",
    )


def test_write_summary_and_readme_happy_path(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)

    # Fake generators: scrivono i file attesi
    def _fake_summary(ctx) -> None:
        (ctx.book_dir / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")

    def _fake_readme(ctx) -> None:
        (ctx.book_dir / "README.md").write_text("# Readme\n", encoding="utf-8")

    monkeypatch.setattr(front, "_gen_summary", _fake_summary, raising=True)
    monkeypatch.setattr(front, "_gen_readme", _fake_readme, raising=True)
    # Validazione: no-op per il test (la funzione reale viene testata altrove)
    monkeypatch.setattr(front, "_validate_md", lambda ctx: None, raising=True)

    front.write_summary_and_readme(
        cast(Any, DummyCtx(repo_root_dir=base, base_dir=base, raw_dir=raw, book_dir=book)),  # duck typing nei test
        logging.getLogger("test"),
        slug="e2e",
    )

    assert (book / "SUMMARY.md").exists()
    assert (book / "README.md").exists()


def test_write_summary_and_readme_generators_fail_raise(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)

    def _boom_summary(ctx) -> None:
        raise ValueError("summary failed")

    def _boom_readme(ctx) -> None:
        raise RuntimeError("readme failed")

    monkeypatch.setattr(front, "_gen_summary", _boom_summary, raising=True)
    monkeypatch.setattr(front, "_gen_readme", _boom_readme, raising=True)

    logger = logging.getLogger("test")
    with pytest.raises(ConversionError) as exc:
        front.write_summary_and_readme(
            cast(Any, DummyCtx(repo_root_dir=base, base_dir=base, raw_dir=raw, book_dir=book)),  # idem sopra
            logger,
            slug="e2e",
        )
    # Il messaggio aggrega gli errori dei generatori
    assert "summary:" in str(exc.value) and "readme:" in str(exc.value)


def test_write_summary_and_readme_logs_errors_with_context(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)

    def _boom_summary(ctx) -> None:
        raise RuntimeError("boom")

    def _ok_readme(ctx) -> None:
        (ctx.book_dir / "README.md").write_text("# Readme\n", encoding="utf-8")

    monkeypatch.setattr(front, "_gen_summary", _boom_summary, raising=True)
    monkeypatch.setattr(front, "_gen_readme", _ok_readme, raising=True)
    monkeypatch.setattr(front, "_validate_md", lambda ctx: None, raising=True)

    logger = logging.getLogger("test.summary")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ConversionError):
            front.write_summary_and_readme(
                cast(Any, DummyCtx(repo_root_dir=base, base_dir=base, raw_dir=raw, book_dir=book)),
                logger,
                slug="e2e",
            )

    for rec in caplog.records:
        if rec.getMessage() == "semantic.summary.failed":
            fp = getattr(rec, "file_path", "")
            slug = getattr(rec, "slug", "")
            assert str(book / "SUMMARY.md") in fp
            assert slug == "e2e"
            break
    else:
        raise AssertionError("expected semantic.summary.failed log")
