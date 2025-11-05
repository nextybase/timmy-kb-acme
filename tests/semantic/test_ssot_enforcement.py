# SPDX-License-Identifier: GPL-3.0-only
# tests/semantic/test_ssot_enforcement.py

import logging

import pytest

from semantic.api import ConfigError, build_markdown_book, enrich_frontmatter


def test_build_markdown_book_handles_missing_vocab(tmp_path, monkeypatch, caplog):
    base = tmp_path
    (base / "raw").mkdir()

    class Ctx:
        base_dir = base

    caplog.set_level(logging.WARNING, "semantic.book")

    monkeypatch.setattr("semantic.api.convert_markdown", lambda context, logger, slug: ["dummy.md"])
    monkeypatch.setattr("semantic.api.write_summary_and_readme", lambda context, logger, slug: None)

    result = build_markdown_book(Ctx(), logger=None, slug="dummy")  # type: ignore[arg-type]
    assert result == ["dummy.md"]
    assert any("semantic.book.vocab_missing" in record.message for record in caplog.records)


def test_enrich_frontmatter_requires_vocab(tmp_path):
    class Ctx:
        base_dir = tmp_path

    logger = logging.getLogger("test.enrich")
    with pytest.raises(ConfigError):
        enrich_frontmatter(Ctx(), logger=logger, vocab={}, slug="dummy")  # type: ignore[arg-type]
