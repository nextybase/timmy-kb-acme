# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Dict, Sequence

from semantic.frontmatter_service import (
    _build_inverse_index,
    _dump_frontmatter,
    _guess_tags_for_name,
    _merge_frontmatter,
    _parse_frontmatter,
)


def test_parse_and_dump_frontmatter_roundtrip() -> None:
    meta = {"title": "Documento di Test", "tags": ["alpha", "beta"]}
    fm = _dump_frontmatter(meta)
    parsed_meta, body = _parse_frontmatter(fm + "Corpo del documento\n")
    assert body.startswith("Corpo del documento")
    assert parsed_meta == meta


def test_parse_frontmatter_no_header_returns_plain() -> None:
    text = "# No header here\ncontent"
    import pytest

    from pipeline.exceptions import ConfigError

    with pytest.raises(ConfigError):
        _parse_frontmatter(text)


def test_merge_frontmatter_preserves_existing_title_and_merges_tags() -> None:
    existing = {"title": "Esistente", "tags": ["b", "a"]}
    merged = _merge_frontmatter(existing, title="Nuovo", tags=["a", "c"])
    # Title preserved, tags merged and sorted unique
    assert merged["title"] == "Esistente"
    assert merged["tags"] == ["a", "b", "c"]


def test_build_inverse_and_guess_tags() -> None:
    vocab: Dict[str, Dict[str, Sequence[str]]] = {
        "analytics": {"aliases": ["analysis", "analitica"]},
        "governance": {"aliases": ["policy", "governance"]},
    }
    inv = _build_inverse_index(vocab)
    # Inverse contains lowercased canon and aliases
    assert inv["analytics"] == {"analytics"}
    assert inv["analitica"] == {"analytics"}
    assert inv["policy"] == {"governance"}

    # Guess from filename-like string (case and separators ignored)
    tags = _guess_tags_for_name("governance_analytics-report.md", vocab, inv=inv)
    assert tags == ["analytics", "governance"]
