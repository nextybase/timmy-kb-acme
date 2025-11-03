# SPDX-License-Identifier: GPL-3.0-only
# tests/semantic/test_ssot_enforcement.py

import logging

import pytest

from semantic.api import ConfigError, build_markdown_book, enrich_frontmatter


def test_build_markdown_book_requires_vocab(tmp_path, monkeypatch, caplog):
    base = tmp_path
    (base / "raw").mkdir()

    # fingi presenza di qualche PDF/MD minimo secondo i tuoi helper di test...
    class Ctx:
        base_dir = base

    with pytest.raises(ConfigError) as ex:
        build_markdown_book(Ctx(), logger=None, slug="dummy")  # type: ignore[arg-type]
    assert "Vocabolario canonico assente" in str(ex.value)


def test_enrich_frontmatter_requires_vocab(tmp_path):
    class Ctx:
        base_dir = tmp_path

    logger = logging.getLogger("test.enrich")
    with pytest.raises(ConfigError):
        enrich_frontmatter(Ctx(), logger=logger, vocab={}, slug="dummy")  # type: ignore[arg-type]
