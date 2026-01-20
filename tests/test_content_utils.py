# SPDX-License-Identifier: GPL-3.0-only
# tests/test_content_utils.py  (aggiunta di due test mirati)
import logging
from pathlib import Path
from typing import Any

import pytest

from pipeline import content_utils as cu
from pipeline.exceptions import PipelineError
from pipeline.frontmatter_utils import read_frontmatter
from semantic.config import SemanticConfig


class _Ctx:
    def __init__(self, base: Path, slug: str = "dummy"):
        self.repo_root_dir = base
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


def test_validate_markdown_dir_missing_has_slug_and_file_path(tmp_path: Path):
    ctx = _Ctx(tmp_path, slug="dummy")
    # md_dir mancante
    with pytest.raises(PipelineError) as ei:
        cu.validate_markdown_dir(ctx, md_dir=tmp_path / "book-missing")
    err = ei.value
    assert getattr(err, "slug", None) == "dummy"
    assert Path(getattr(err, "file_path", "")) == (tmp_path / "book-missing")


def test_validate_markdown_dir_not_directory_has_slug_and_file_path(tmp_path: Path):
    ctx = _Ctx(tmp_path, slug="dummy")
    file_path = tmp_path / "book-file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(PipelineError) as ei:
        cu.validate_markdown_dir(ctx, md_dir=file_path)
    err = ei.value
    assert getattr(err, "slug", None) == "dummy"
    assert Path(getattr(err, "file_path", "")) == file_path


def test_validate_markdown_dir_traversal_includes_slug_in_message(tmp_path: Path):
    base = tmp_path / "kb"
    base.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside_book"
    outside.mkdir(parents=True, exist_ok=True)

    ctx = _Ctx(base, slug="dummy")
    with pytest.raises(PipelineError) as ei:
        cu.validate_markdown_dir(ctx, md_dir=outside)

    err = ei.value
    assert getattr(err, "slug", None) == "dummy"
    assert "slug=dummy" in str(err)


def test_extract_pdf_text_raises_on_empty(tmp_path: Path, monkeypatch: Any) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr("nlp.nlp_keywords.extract_text_from_pdf", lambda _path: "  ")
    logger = logging.getLogger("test.content.extract")
    with pytest.raises(PipelineError, match="empty content"):
        cu._extract_pdf_text(pdf_path, slug="dummy", logger=logger)


def test_extract_pdf_text_raises_on_failure(tmp_path: Path, monkeypatch: Any) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    def _boom(_path: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("nlp.nlp_keywords.extract_text_from_pdf", _boom)
    logger = logging.getLogger("test.content.extract")
    with pytest.raises(PipelineError, match="extraction failed"):
        cu._extract_pdf_text(pdf_path, slug="dummy", logger=logger)


def test_extract_pdf_text_real_path_success(tmp_path: Path, monkeypatch: Any) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%dummy\n")

    def _fake_extract(_path: str) -> str:
        return "Testo reale estratto dal PDF"

    monkeypatch.setattr("nlp.nlp_keywords.extract_text_from_pdf", _fake_extract)
    logger = logging.getLogger("test.content.realpath")
    text = cu._extract_pdf_text(pdf_path, slug="dummy", logger=logger)
    assert "Testo reale estratto" in text


def test_write_markdown_for_pdf_preserves_created_at(tmp_path: Path, monkeypatch: Any):
    ctx = _Ctx(tmp_path, slug="dummy")
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    pdf_path = raw_root / "documento.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    target_root = tmp_path / "book"
    cfg = SemanticConfig(
        base_dir=tmp_path,
        semantic_dir=tmp_path / "semantic",
        raw_dir=raw_root,
    )

    rel_pdf = pdf_path.relative_to(raw_root).as_posix()
    candidates = {rel_pdf: {"tags": ["inaugurazione", "vision"]}}
    monkeypatch.setattr(cu, "_extract_pdf_text", lambda *args, **kwargs: "contenuto pdf")

    first_md = cu._write_markdown_for_pdf(pdf_path, raw_root, target_root, candidates, cfg, slug=ctx.slug)
    meta_before, body_before = read_frontmatter(target_root, first_md)
    created_before = meta_before["created_at"]

    def _fail_write(*_args, **_kwargs) -> None:
        raise AssertionError("safe_write_text should not be called for idempotent Markdown")

    monkeypatch.setattr(cu, "safe_write_text", _fail_write)
    second_md = cu._write_markdown_for_pdf(pdf_path, raw_root, target_root, candidates, cfg, slug=ctx.slug)

    assert second_md == first_md
    meta_after, body_after = read_frontmatter(target_root, second_md, use_cache=False)
    assert meta_after["created_at"] == created_before
    assert body_after == body_before


def test_write_markdown_for_pdf_uses_cache_when_unchanged(tmp_path: Path, monkeypatch: Any) -> None:
    cu.clear_frontmatter_cache()

    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    pdf_path = raw_root / "documento.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    target_root = tmp_path / "book"
    cfg = SemanticConfig(
        base_dir=tmp_path,
        semantic_dir=tmp_path / "semantic",
        raw_dir=raw_root,
    )

    rel_pdf = pdf_path.relative_to(raw_root).as_posix()
    candidates = {rel_pdf: {"tags": ["inaugurazione", "vision"]}}
    monkeypatch.setattr(cu, "_extract_pdf_text", lambda *args, **kwargs: "contenuto pdf")

    first_md = cu._write_markdown_for_pdf(pdf_path, raw_root, target_root, candidates, cfg, slug="dummy")
    meta_before, body_before = read_frontmatter(target_root, first_md, use_cache=False)

    stat = first_md.stat()
    cache_key = (first_md, stat.st_mtime_ns, stat.st_size)
    cu._FRONTMATTER_CACHE.set(cache_key, (meta_before, body_before))

    def _fail_read(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("read_frontmatter dovrebbe essere bypassata con cache")

    def _fail_write(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("safe_write_text non deve essere richiamata se il contenuto non cambia")

    monkeypatch.setattr(cu, "read_frontmatter", _fail_read)
    monkeypatch.setattr(cu, "safe_write_text", _fail_write)

    second_md = cu._write_markdown_for_pdf(pdf_path, raw_root, target_root, candidates, cfg, slug="dummy")

    cached_entry = cu._FRONTMATTER_CACHE.get(cache_key)
    assert cached_entry is not None
    cached_meta, cached_body = cached_entry
    assert second_md == first_md
    assert cached_meta["created_at"] == meta_before["created_at"]
    assert cached_body == body_before

    cu.clear_frontmatter_cache()


def test_write_markdown_for_pdf_adds_excerpt_when_available(tmp_path: Path, monkeypatch: Any) -> None:
    ctx = _Ctx(tmp_path, slug="dummy")
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    pdf_path = raw_root / "documento.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    target_root = tmp_path / "book"
    cfg = SemanticConfig(
        base_dir=tmp_path,
        semantic_dir=tmp_path / "semantic",
        raw_dir=raw_root,
    )

    rel_pdf = pdf_path.relative_to(raw_root).as_posix()
    candidates = {rel_pdf: {"tags": ["inaugurazione", "vision"]}}
    excerpt_text = "Testo estratto e normalizzato"
    monkeypatch.setattr(cu, "_extract_pdf_text", lambda *args, **kwargs: "contenuto pdf")
    monkeypatch.setattr(cu, "_extract_pdf_excerpt", lambda *args, **kwargs: excerpt_text)

    md = cu._write_markdown_for_pdf(
        pdf_path,
        raw_root,
        target_root,
        candidates,
        cfg,
        slug=ctx.slug,
    )

    meta, body = read_frontmatter(target_root, md, use_cache=False)
    assert excerpt_text in body


def test_write_markdown_for_pdf_inserts_chunk_sections(tmp_path: Path, monkeypatch: Any) -> None:
    ctx = _Ctx(tmp_path, slug="dummy")
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    pdf_path = raw_root / "documento.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    target_root = tmp_path / "book"
    cfg = SemanticConfig(
        base_dir=tmp_path,
        semantic_dir=tmp_path / "semantic",
        raw_dir=raw_root,
    )
    long_text = "chunk " * 500
    monkeypatch.setattr(cu, "_extract_pdf_text", lambda *args, **kwargs: long_text)

    md = cu._write_markdown_for_pdf(
        pdf_path,
        raw_root,
        target_root,
        {pdf_path.name: {}},
        cfg,
        slug=ctx.slug,
    )

    meta, body = read_frontmatter(target_root, md, use_cache=False)
    assert "### Chunk 1" in body
    assert meta.get("content_chunks")
    assert meta["content_chunks"][0].startswith("chunk")
