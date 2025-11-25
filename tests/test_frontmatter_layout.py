# SPDX-License-Identifier: GPL-3.0-only
import logging
from pathlib import Path

from pipeline.frontmatter_utils import read_frontmatter
from semantic import frontmatter_service as front


def test_load_vision_text_reads_existing_file(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "vision_statement.yaml").write_text("testo", encoding="utf-8")

    assert front._load_vision_text(tmp_path) == "testo"


def test_load_vision_text_returns_empty_when_missing(tmp_path: Path) -> None:
    assert front._load_vision_text(tmp_path) == ""


def test_build_layout_constraints_uses_keys(tmp_path: Path) -> None:
    mapping = {"Strategy": {}, "data": {}, "": {}}

    constraints = front._build_layout_constraints(mapping)

    assert constraints["max_depth"] == 3
    assert constraints["max_nodes"] >= 12
    assert sorted(constraints["allowed_prefixes"]) == ["data", "strategy"]
    assert isinstance(constraints["semantic_mapping"]["strategy"], tuple)
    assert "operations" not in constraints["semantic_mapping"]


def test_build_layout_constraints_falls_back(tmp_path: Path) -> None:
    constraints = front._build_layout_constraints({})
    assert set(constraints["allowed_prefixes"]) == {"operations", "strategy", "data"}


def test_append_layout_note_to_readme(tmp_path: Path) -> None:
    base_dir = tmp_path
    book_dir = base_dir / "book"
    book_dir.mkdir()
    readme = book_dir / "README.md"
    readme.write_text("# KB\n", encoding="utf-8")

    semantic_dir = base_dir / "semantic"
    semantic_dir.mkdir()
    layout = semantic_dir / "layout_proposal.yaml"
    layout.write_text("strategy:\n  overview: {}\ndata:\n  datasets: {}", encoding="utf-8")

    front._append_layout_note_to_readme(base_dir, book_dir, logging.getLogger("test"), slug="dummy")

    content = readme.read_text(encoding="utf-8")
    assert "Struttura semantica proposta" in content
    assert "- data" in content
    assert "- strategy" in content

    # Calling again should not duplicate note
    front._append_layout_note_to_readme(base_dir, book_dir, logging.getLogger("test"), slug="dummy")
    assert content == readme.read_text(encoding="utf-8")


def test_layout_section_from_md_lookup(tmp_path: Path) -> None:
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    md_path = book_dir / "data" / "doc.md"
    md_path.parent.mkdir(parents=True)
    md_path.write_text("content", encoding="utf-8")

    section = front._layout_section_from_md(md_path, book_dir, ["strategy", "data"])
    assert section == "data"
    assert front._layout_section_from_md(book_dir / "doc.md", book_dir, ["strategy", "data"]) is None


def test_enrich_frontmatter_sets_layout_section(tmp_path: Path) -> None:
    class Ctx:
        def __init__(self, base: Path):
            self.base_dir = base
            self.raw_dir = base / "raw"
            self.md_dir = base / "book"
            self.slug = "dummy"

    base_dir = tmp_path
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True)
    doc_dir = book_dir / "strategy"
    doc_dir.mkdir(parents=True)
    doc_path = doc_dir / "doc.md"
    doc_path.write_text("---\ntags_raw: [strategy]\n---\nbody\n", encoding="utf-8")

    semantic_dir = base_dir / "semantic"
    semantic_dir.mkdir(parents=True)
    layout = semantic_dir / "layout_proposal.yaml"
    layout.write_text("strategy:\n  overview: {}\n", encoding="utf-8")

    ctx = Ctx(base_dir)
    vocab = {"strategy": {"aliases": []}}
    touched = front.enrich_frontmatter(ctx, logging.getLogger("test"), vocab, slug="dummy", allow_empty_vocab=True)

    assert doc_path in touched
    meta, _ = read_frontmatter(book_dir, doc_path, use_cache=False)
    assert meta.get("layout_section") == "strategy"


def test_write_layout_summary_creates_file(tmp_path: Path) -> None:
    base_dir = tmp_path
    book_dir = base_dir / "book"
    book_dir.mkdir()
    md_dir = book_dir
    semantic_dir = base_dir / "semantic"
    semantic_dir.mkdir()
    layout = semantic_dir / "layout_proposal.yaml"
    layout.write_text("strategy:\n  overview: {}\n", encoding="utf-8")

    front._write_layout_summary(base_dir, md_dir, logging.getLogger("test"), slug="dummy")

    summary = book_dir / "layout_summary.md"
    assert summary.exists()
    content = summary.read_text(encoding="utf-8")
    assert "- **strategy**" in content
