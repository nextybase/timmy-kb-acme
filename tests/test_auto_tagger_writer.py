# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import PathTraversalError
from semantic.auto_tagger import render_tags_csv


def _candidates_min() -> dict[str, dict[str, object]]:
    return {
        "raw/a.pdf": {
            "tags": ["alpha", "beta"],
            "entities": [],
            "keyphrases": [],
            "score": {"alpha": 1.0, "beta": 0.6},
            "sources": {"path": ["raw"], "filename": ["a"]},
        }
    }


def test_render_tags_csv_happy_path(dummy_workspace):
    base: Path = dummy_workspace["base"]
    sem: Path = dummy_workspace["semantic_mapping"].parent
    csv_path = sem / "tags_raw.csv"

    render_tags_csv(_candidates_min(), csv_path, perimeter_root=base)

    assert csv_path.exists()
    text = csv_path.read_text(encoding="utf-8")
    assert "relative_path" in text.splitlines()[0]
    assert "raw/a.pdf" in text


def test_render_tags_csv_blocks_outside_base(dummy_workspace):
    base: Path = dummy_workspace["base"]
    outside_csv = base.parent / "outside.csv"

    with pytest.raises(PathTraversalError):
        render_tags_csv(_candidates_min(), outside_csv, perimeter_root=base)
