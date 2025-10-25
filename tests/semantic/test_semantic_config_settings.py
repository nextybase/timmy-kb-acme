from __future__ import annotations

from pathlib import Path

import pytest

from semantic.config import load_semantic_config

pytestmark = pytest.mark.semantic


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_semantic_config_merges_settings(tmp_path: Path) -> None:
    base_dir = tmp_path / "output" / "timmy-kb-acme"
    config_yaml = base_dir / "config" / "config.yaml"
    mapping_yaml = base_dir / "semantic" / "semantic_mapping.yaml"

    _write_file(
        config_yaml,
        """
semantic_defaults:
  top_k: 7
  score_min: 0.55
"""
        + "\n",
    )
    _write_file(
        mapping_yaml,
        """
semantic_tagger:
  top_k: 9
  stop_tags:
    - bozza
"""
        + "\n",
    )

    cfg = load_semantic_config(base_dir)
    assert cfg.top_k == 9
    assert cfg.score_min == 0.55
    assert "semantic_tagger" in cfg.mapping
