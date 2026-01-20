# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import semantic.core as se
from pipeline.exceptions import EnrichmentError, PipelineError


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj") -> None:
        self.repo_root_dir = base
        self.base_dir = base
        self.md_dir = base / "book"
        self.slug = slug
        self.enrich_enabled = True


def test_enrich_markdown_folder_raises_on_first_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\nBody\n", encoding="utf-8")

    def _boom(_ctx: object, _file: Path, _logger: logging.Logger) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(se, "_enrich_md", _boom)

    with pytest.raises(EnrichmentError):
        se.enrich_markdown_folder(_Ctx(base), logging.getLogger("test.enrich.strict"))


def test_extract_semantic_concepts_raises_on_read_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "doc.md").write_text("# Doc\n", encoding="utf-8")

    monkeypatch.setattr(se, "load_semantic_mapping", lambda _ctx, logger=None: {"persona": ["nome"]})

    def _read_boom(_base: Path, _path: Path, encoding: str = "utf-8") -> str:
        raise OSError("nope")

    monkeypatch.setattr(se, "read_text_safe", _read_boom)

    with pytest.raises(PipelineError):
        se.extract_semantic_concepts(_Ctx(base))
