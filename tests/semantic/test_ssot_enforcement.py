# SPDX-License-Identifier: GPL-3.0-or-later
# tests/semantic/test_ssot_enforcement.py

import logging

import pytest

from semantic.api import ConfigError, build_markdown_book, enrich_frontmatter


def test_build_markdown_book_requires_vocab(tmp_path, monkeypatch):
    base = tmp_path
    (base / "raw").mkdir()

    class Ctx:
        base_dir = base

    monkeypatch.setattr("semantic.api.convert_markdown", lambda context, logger, slug: ["dummy.md"])
    monkeypatch.setattr("semantic.api.write_summary_and_readme", lambda context, logger, slug: None)

    with pytest.raises(ConfigError):
        build_markdown_book(Ctx(), logger=None, slug="dummy")  # type: ignore[arg-type]


def test_enrich_frontmatter_requires_vocab(tmp_path):
    class Ctx:
        base_dir = tmp_path

    logger = logging.getLogger("test.enrich")
    with pytest.raises(ConfigError):
        enrich_frontmatter(Ctx(), logger=logger, vocab={}, slug="dummy")  # type: ignore[arg-type]
