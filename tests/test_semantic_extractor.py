# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_extractor.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast

import pytest

import semantic.semantic_extractor as se
from pipeline.exceptions import InputDirectoryMissing, PipelineError
from semantic.semantic_extractor import _list_markdown_files, extract_semantic_concepts


@dataclass
class DummyCtx:
    # Minimal context carrying only the needed attributes (duck-typed)
    slug: str = "dummy"
    base_dir: Optional[Path] = None
    md_dir: Optional[Path] = None
    # For extract_semantic_concepts -> load_semantic_mapping
    config_dir: Optional[Path] = None
    repo_root_dir: Optional[Path] = None


def test__list_markdown_files_happy_path(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    md.mkdir(parents=True)
    # Create files (only .md should be listed; sorted)
    (md / "b.md").write_text("B", encoding="utf-8")
    (md / "a.md").write_text("A", encoding="utf-8")
    (md / "c.txt").write_text("X", encoding="utf-8")

    ctx = DummyCtx(base_dir=base, md_dir=md)
    files = _list_markdown_files(cast(Any, ctx))
    assert [p.name for p in files] == ["a.md", "b.md"]


def test__list_markdown_files_missing_fields_raises() -> None:
    # Missing md_dir/base_dir -> PipelineError
    with pytest.raises(PipelineError):
        _ = _list_markdown_files(cast(Any, DummyCtx(base_dir=None, md_dir=None)))


def test__list_markdown_files_unsafe_path_raises(tmp_path: Path) -> None:
    base = tmp_path / "safe"
    base.mkdir()
    # md_dir outside base -> unsafe
    md_outside = tmp_path / "outside"
    md_outside.mkdir()
    with pytest.raises(PipelineError):
        _ = _list_markdown_files(cast(Any, DummyCtx(base_dir=base, md_dir=md_outside)))


def test__list_markdown_files_missing_dir_raises(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    base.mkdir()
    # md does not exist
    with pytest.raises(InputDirectoryMissing):
        _ = _list_markdown_files(cast(Any, DummyCtx(base_dir=base, md_dir=md)))


def _publish_tags(tags: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    mapping: dict[str, dict[str, list[str]]] = {}
    for tag in tags:
        name = tag["name"]
        aliases = list(tag.get("synonyms") or [])
        mapping[name] = {"aliases": aliases}
    return mapping


def _apply_vocab(monkeypatch: pytest.MonkeyPatch, tags: list[dict[str, Any]]) -> None:
    mapping = _publish_tags(tags)
    monkeypatch.setattr(se, "load_reviewed_vocab", lambda base_dir, logger: mapping)


def test_extract_semantic_concepts_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    md.mkdir(parents=True)
    # Create markdown files
    (md / "one.md").write_text("Foo and BAR appear here", encoding="utf-8")
    (md / "two.md").write_text("baz and qux", encoding="utf-8")
    (md / "three.md").write_text("FOO only", encoding="utf-8")

    # Tags reviewed (Fase 2): due concetti con keywords (ordine rilevante per first-hit)
    _apply_vocab(
        monkeypatch,
        [
            {"name": "conceptA", "action": "keep", "synonyms": ["foo", "Bar", "Foo"]},
            {"name": "conceptB", "action": "keep", "synonyms": ["qux"]},
        ],
    )

    ctx = DummyCtx(slug="s1", base_dir=base, md_dir=md, config_dir=None, repo_root_dir=tmp_path)
    out = extract_semantic_concepts(cast(Any, ctx))
    print(out)

    # For conceptA: first-hit policy per file ->
    # - one.md contains both 'foo' and 'bar' -> first in mapping order is 'foo'
    # - three.md contains 'FOO' -> matches 'foo' (case-insensitive), reported as original 'foo'
    assert {d["file"] for d in out["conceptA"]} == {"one.md", "three.md"}
    assert all(d["keyword"] == "foo" for d in out["conceptA"])  # both hits attributed to 'foo'

    # For conceptB: only two.md contains 'qux'
    assert out["conceptB"] == [{"file": "two.md", "keyword": "qux"}]


def test_extract_semantic_concepts_respects_max_scan_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    md.mkdir(parents=True)

    # Small file (should be scanned)
    (md / "small.md").write_text("alpha beta", encoding="utf-8")
    # Big file (should be skipped)
    big = md / "big.md"
    big.write_text("alpha\n" * 10_000, encoding="utf-8")

    _apply_vocab(
        monkeypatch,
        [
            {"name": "concept", "action": "keep", "synonyms": ["alpha"]},
        ],
    )
    ctx = DummyCtx(slug="s2", base_dir=base, md_dir=md, config_dir=None, repo_root_dir=tmp_path)

    # Set threshold lower than big file size but higher than small
    out = extract_semantic_concepts(cast(Any, ctx), max_scan_bytes=1024)
    assert out["concept"] == [{"file": "small.md", "keyword": "alpha"}]


def test_extract_semantic_concepts_short_circuits_on_empty_mapping(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    cfg = base / "config"
    md.mkdir(parents=True)
    (md / "x.md").write_text("irrelevant", encoding="utf-8")

    # Force load_semantic_mapping to return empty mapping to test short-circuit
    import semantic.semantic_extractor as se

    monkeypatch.setattr(se, "load_semantic_mapping", lambda context, logger=None: {})

    ctx = DummyCtx(slug="s3", base_dir=base, md_dir=md, config_dir=cfg, repo_root_dir=tmp_path)
    out = extract_semantic_concepts(cast(Any, ctx))
    assert out == {}


def test_extract_semantic_concepts_matches_canonical_without_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "kb2"
    md = base / "book"
    md.mkdir(parents=True)
    (md / "solo.md").write_text("Cloud services overview", encoding="utf-8")

    _apply_vocab(
        monkeypatch,
        [
            {"name": "Cloud", "action": "keep", "synonyms": []},
        ],
    )

    ctx = DummyCtx(slug="s2", base_dir=base, md_dir=md, config_dir=None, repo_root_dir=tmp_path)
    out = extract_semantic_concepts(cast(Any, ctx))
    assert out["Cloud"] == [{"file": "solo.md", "keyword": "Cloud"}]
