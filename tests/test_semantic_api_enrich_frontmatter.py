# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_api_enrich_frontmatter.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Sequence, cast

from semantic import frontmatter_service as front


@dataclass
class DummyCtx:
    repo_root_dir: Path
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str = "e2e"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_minimal_layout(base: Path) -> None:
    _write(base / "config" / "config.yaml", "meta:\n  client_name: test\n")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    _write(base / "book" / "README.md", "# KB\n")
    _write(base / "book" / "SUMMARY.md", "# Summary\n")
    _write(base / "semantic" / "semantic_mapping.yaml", "{}")


def test_enrich_frontmatter_end_to_end(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    _write_minimal_layout(base)
    # Prepare two MD files: one without frontmatter, one with existing frontmatter
    _write(book / "data_governance-intro.md", "---\ntitle:\n---\nBody A\n")
    existing = (
        "---\n"
        "title: Existing Title\n"
        "tags:\n"
        "  - alpha\n"
        "tags_raw:\n"
        "  - Policy\n"
        "  - analysis\n"
        "---\n"
        "Existing body\n"
    )
    _write(book / "analytics_report.md", existing)
    _write(book / "risk" / "analytics_nested.md", "---\ntitle:\n---\nNested body\n")

    # Minimal vocab with aliases; both canon and alias should map back to canon
    vocab: Dict[str, Dict[str, Sequence[str]]] = {
        "governance": {"aliases": ["policy", "governance"]},
        "analytics": {"aliases": ["analytics", "analysis"]},
    }

    touched = front.enrich_frontmatter(
        cast(
            Any, DummyCtx(repo_root_dir=base, base_dir=base, raw_dir=base / "raw", md_dir=book)
        ),  # duck typing nei test
        logging.getLogger("test"),
        vocab,
        slug="e2e",
    )

    # Both files should be processed (one already had frontmatter, but tags/title may change)
    names = {p.relative_to(book).as_posix() for p in touched}
    assert {"data_governance-intro.md", "analytics_report.md", "risk/analytics_nested.md"}.issubset(names)

    # Verify first file: title inferred from filename, tags include governance
    text_a = (book / "data_governance-intro.md").read_text(encoding="utf-8")
    meta_a, body_a = front._parse_frontmatter(text_a)
    assert meta_a.get("title") == "data governance intro"
    assert "governance" in (meta_a.get("tags") or [])
    assert body_a.strip() == "Body A"

    # Verify second file: title preserved, tags merged (alpha + analytics)
    text_b = (book / "analytics_report.md").read_text(encoding="utf-8")
    meta_b, body_b = front._parse_frontmatter(text_b)
    assert meta_b.get("title") == "Existing Title"
    tags_b = set(meta_b.get("tags") or [])
    assert tags_b >= {"alpha", "analytics", "governance"}
    assert meta_b.get("tags_raw") == ["Policy", "analysis"]
    assert "Existing body" in body_b

    text_nested = (book / "risk" / "analytics_nested.md").read_text(encoding="utf-8")
    meta_nested, body_nested = front._parse_frontmatter(text_nested)
    assert meta_nested.get("title") == "analytics nested"
    tags_nested = set(meta_nested.get("tags") or [])
    assert "analytics" in tags_nested
    assert body_nested.strip() == "Nested body"
