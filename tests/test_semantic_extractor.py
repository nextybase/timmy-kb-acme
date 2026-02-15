# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_semantic_extractor.py
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast

import pytest

import semantic.core as se
from pipeline.exceptions import InputDirectoryMissing, PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.workspace_layout import WorkspaceLayout
from semantic.core import _list_markdown_files, extract_semantic_concepts
from tests.conftest import build_vocab_db
from tests.utils.workspace import ensure_minimal_workspace_layout


@dataclass
class DummyCtx:
    # Minimal context carrying only the needed attributes (duck-typed)
    slug: str = "dummy"
    base_dir: Optional[Path] = None
    book_dir: Optional[Path] = None
    # For extract_semantic_concepts -> load_semantic_mapping
    config_dir: Optional[Path] = None
    repo_root_dir: Optional[Path] = None


def _prepare_layout(base: Path, book_dir: Path, *, strict: bool) -> None:
    book_dir.mkdir(parents=True, exist_ok=True)
    ensure_minimal_workspace_layout(base, client_name="test")
    if not strict:
        return
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}\n", encoding="utf-8")
    (book_dir / "README.md").write_text("README", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("SUMMARY", encoding="utf-8")


def test__list_markdown_files_happy_path(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    _prepare_layout(base, md, strict=False)
    # Create files (only .md should be listed; sorted)
    (md / "b.md").write_text("B", encoding="utf-8")
    (md / "a.md").write_text("A", encoding="utf-8")
    (md / "c.txt").write_text("X", encoding="utf-8")

    ctx = DummyCtx(base_dir=base, book_dir=md, repo_root_dir=base)
    files = _list_markdown_files(
        cast(Any, ctx),
        get_structured_logger("tests.semantic_extractor.list_md", context=ctx),
    )
    assert [p.name for p in files] == ["a.md", "b.md", "README.md", "SUMMARY.md"]


def test__list_markdown_files_missing_fields_raises() -> None:
    # Missing book_dir/base_dir -> PipelineError
    with pytest.raises(PipelineError):
        _ = _list_markdown_files(
            cast(Any, DummyCtx(base_dir=None, book_dir=None)),
            get_structured_logger("tests.semantic_extractor.list_md", context=DummyCtx()),
        )


def test__list_markdown_files_unsafe_path_raises(tmp_path: Path) -> None:
    base = tmp_path / "safe"
    md = base / "book"
    _prepare_layout(base, md, strict=False)
    # Create at least one markdown file in canonical book dir
    (md / "x.md").write_text("X", encoding="utf-8")

    # book_dir outside base (non-canonical) -> must be ignored in Beta contract
    md_outside = tmp_path / "outside"
    md_outside.mkdir()
    files = _list_markdown_files(
        cast(Any, DummyCtx(base_dir=base, book_dir=md_outside, repo_root_dir=base)),
        get_structured_logger(
            "tests.semantic_extractor.list_md",
            context=DummyCtx(base_dir=base, book_dir=md_outside, repo_root_dir=base),
        ),
    )
    # Must list from canonical layout.book_dir, not context override
    assert any(p.name == "x.md" for p in files)


def test__list_markdown_files_missing_dir_raises(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    ensure_minimal_workspace_layout(base, client_name="test")
    layout = WorkspaceLayout.from_context(DummyCtx(base_dir=base, book_dir=md, repo_root_dir=base))
    shutil.rmtree(md)
    # canonical layout.book_dir missing => InputDirectoryMissing
    with pytest.raises(InputDirectoryMissing):
        _ = _list_markdown_files(
            cast(Any, DummyCtx(base_dir=base, book_dir=None, repo_root_dir=base)),
            get_structured_logger(
                "tests.semantic_extractor.list_md",
                context=DummyCtx(base_dir=base, book_dir=None, repo_root_dir=base),
            ),
            layout=layout,
        )


def test_extract_semantic_concepts_happy_path(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    _prepare_layout(base, md, strict=True)
    # Create markdown files
    (md / "one.md").write_text("Foo and BAR appear here", encoding="utf-8")
    (md / "two.md").write_text("baz and qux", encoding="utf-8")
    (md / "three.md").write_text("FOO only", encoding="utf-8")

    # Tags reviewed (Fase 2): due concetti con keywords (ordine rilevante per first-hit)
    db_path = build_vocab_db(
        base,
        [
            {"name": "conceptA", "action": "keep", "synonyms": ["foo", "Bar", "Foo"]},
            {"name": "conceptB", "action": "keep", "synonyms": ["qux"]},
        ],
    )
    assert Path(db_path).exists()

    ctx = DummyCtx(slug="s1", base_dir=base, book_dir=md, config_dir=None, repo_root_dir=base)
    out = extract_semantic_concepts(cast(Any, ctx))

    # For conceptA: first-hit policy per file ->
    # - one.md contains both 'foo' and 'bar' -> first in mapping order is 'foo'
    # - three.md contains 'FOO' -> matches 'foo' (case-insensitive), reported as original 'foo'
    assert {d["file"] for d in out["conceptA"]} == {"one.md", "three.md"}
    assert all(d["keyword"] == "foo" for d in out["conceptA"])  # both hits attributed to 'foo'

    # For conceptB: only two.md contains 'qux'
    assert out["conceptB"] == [{"file": "two.md", "keyword": "qux"}]


def test_extract_semantic_concepts_respects_max_scan_bytes(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    _prepare_layout(base, md, strict=True)

    # Small file (should be scanned)
    (md / "small.md").write_text("alpha beta", encoding="utf-8")
    # Big file (should be skipped)
    big = md / "big.md"
    big.write_text("alpha\n" * 10_000, encoding="utf-8")

    db_path = build_vocab_db(
        base,
        [
            {"name": "concept", "action": "keep", "synonyms": ["alpha"]},
        ],
    )
    assert Path(db_path).exists()
    ctx = DummyCtx(slug="s2", base_dir=base, book_dir=md, config_dir=None, repo_root_dir=base)

    # Set threshold lower than big file size but higher than small
    out = extract_semantic_concepts(cast(Any, ctx), max_scan_bytes=1024)
    assert out["concept"] == [{"file": "small.md", "keyword": "alpha"}]


def test_extract_semantic_concepts_short_circuits_on_empty_mapping(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    cfg = base / "config"
    _prepare_layout(base, md, strict=True)
    (md / "x.md").write_text("irrelevant", encoding="utf-8")

    # Force load_semantic_mapping to return empty mapping to test short-circuit

    monkeypatch.setattr(se, "load_semantic_mapping", lambda context, logger=None: {})

    ctx = DummyCtx(slug="s3", base_dir=base, book_dir=md, config_dir=cfg, repo_root_dir=base)
    out = extract_semantic_concepts(cast(Any, ctx))
    assert out == {}


def test_load_semantic_mapping_requires_tags_db(tmp_path: Path) -> None:
    base = tmp_path / "kb_missing"
    book = base / "book"
    _prepare_layout(base, book, strict=True)
    (book / "noop.md").write_text("stub", encoding="utf-8")
    ctx = DummyCtx(slug="missing", base_dir=base, book_dir=book, config_dir=None, repo_root_dir=base)
    with pytest.raises(PipelineError):
        se.load_semantic_mapping(cast(Any, ctx))


def test_extract_semantic_concepts_matches_canonical_without_aliases(tmp_path: Path) -> None:
    base = tmp_path / "kb2"
    md = base / "book"
    _prepare_layout(base, md, strict=True)
    (md / "solo.md").write_text("Cloud services overview", encoding="utf-8")

    db_path = build_vocab_db(
        base,
        [
            {"name": "Cloud", "action": "keep", "synonyms": []},
        ],
    )
    assert Path(db_path).exists()

    ctx = DummyCtx(slug="s2", base_dir=base, book_dir=md, config_dir=None, repo_root_dir=base)
    out = extract_semantic_concepts(cast(Any, ctx))
    assert out["Cloud"] == [{"file": "solo.md", "keyword": "Cloud"}]


def test_extract_semantic_concepts_db_first(tmp_path: Path) -> None:
    base = tmp_path / "kb_db"
    book = base / "book"
    _prepare_layout(base, book, strict=True)
    (book / "concept.md").write_text("Foo canonicalOnly and BAR example", encoding="utf-8")

    db_path = build_vocab_db(
        base,
        [
            {"name": "conceptA", "action": "keep", "synonyms": ["foo", "Bar"]},
            {"name": "canonicalOnly", "action": "keep", "synonyms": []},
        ],
    )
    assert Path(db_path).exists()

    ctx = DummyCtx(slug="db", base_dir=base, book_dir=book, config_dir=None, repo_root_dir=base)
    out = extract_semantic_concepts(cast(Any, ctx))

    assert {d["file"] for d in out["conceptA"]} == {"concept.md"}
    assert all(d["keyword"] == "foo" for d in out["conceptA"])
    assert out["canonicalOnly"] == [{"file": "concept.md", "keyword": "canonicalOnly"}]


def test_extract_semantic_concepts_respects_duplicate_aliases(tmp_path: Path) -> None:
    base = tmp_path / "kb_alias"
    book = base / "book"
    _prepare_layout(base, book, strict=True)
    (book / "dup.md").write_text("foo, latest", encoding="utf-8")

    db_path = build_vocab_db(
        base,
        [
            {"name": "conceptA", "action": "keep", "synonyms": ["foo", "foo", "Bar"]},
        ],
    )
    assert Path(db_path).exists()

    ctx = DummyCtx(slug="dup", base_dir=base, book_dir=book, config_dir=None, repo_root_dir=base)
    out = extract_semantic_concepts(cast(Any, ctx))

    assert out["conceptA"] == [{"file": "dup.md", "keyword": "foo"}]


def test_extract_semantic_concepts_handles_merge_into(tmp_path: Path) -> None:
    base = tmp_path / "kb_merge"
    book = base / "book"
    _prepare_layout(base, book, strict=True)
    (book / "legacy.md").write_text("Legacy Cloud stack", encoding="utf-8")
    db_path = build_vocab_db(
        base,
        [
            {"name": "Cloud", "action": "keep", "synonyms": ["cloud"]},
            {"name": "Legacy Cloud", "action": "merge_into:Cloud", "synonyms": ["legacy cloud"]},
        ],
    )
    assert Path(db_path).exists()
    ctx = DummyCtx(slug="merge", base_dir=base, book_dir=book, config_dir=None, repo_root_dir=base)
    out = extract_semantic_concepts(cast(Any, ctx))
    assert out["Cloud"] == [{"file": "legacy.md", "keyword": "cloud"}]


def test_extract_semantic_concepts_handles_nested_merge(tmp_path: Path) -> None:
    base = tmp_path / "kb_nested"
    book = base / "book"
    _prepare_layout(base, book, strict=True)
    (book / "core.md").write_text("Legacy Cloud Platform", encoding="utf-8")
    db_path = build_vocab_db(
        base,
        [
            {"name": "Cloud", "action": "keep", "synonyms": ["cloud"]},
            {"name": "Cloud Platform", "action": "merge_into:Cloud", "synonyms": ["platform"]},
            {"name": "Legacy Cloud Platform", "action": "merge_into:Cloud Platform", "synonyms": ["legacy platform"]},
        ],
    )
    assert Path(db_path).exists()
    ctx = DummyCtx(slug="nested", base_dir=base, book_dir=book, config_dir=None, repo_root_dir=base)
    out = extract_semantic_concepts(cast(Any, ctx))
    combined = out.get("Cloud", []) + out.get("Cloud Platform", [])
    assert len(combined) == 1
    assert combined[0]["file"] == "core.md"
    assert combined[0]["keyword"].lower() in {"cloud", "cloud platform"}
    assert out.get("Legacy Cloud Platform", []) == []


def test_extract_semantic_concepts_merge_preserves_priority(tmp_path: Path) -> None:
    base = tmp_path / "kb_merge_order"
    book = base / "book"
    _prepare_layout(base, book, strict=True)
    (book / "sample.md").write_text("first Cloud legacy roadmap", encoding="utf-8")
    build_vocab_db(
        base,
        [
            {"name": "Cloud", "action": "keep", "synonyms": ["first"]},
        ],
    )
    db_path = build_vocab_db(
        base,
        [
            {"name": "Cloud", "action": "keep", "synonyms": ["second"]},
        ],
    )
    assert Path(db_path).exists()
    ctx = DummyCtx(slug="merge", base_dir=base, book_dir=book, config_dir=None, repo_root_dir=base)
    out = extract_semantic_concepts(cast(Any, ctx))
    assert out["Cloud"][0]["keyword"] == "first"

    with sqlite3.connect(db_path) as conn:
        term_id = conn.execute("SELECT id FROM tags WHERE name=?", ("Cloud",)).fetchone()[0]
        rows = list(
            conn.execute(
                "SELECT alias FROM tag_synonyms WHERE tag_id=? ORDER BY pos ASC",
                (term_id,),
            )
        )
    assert [row[0] for row in rows] == ["first", "second"]
