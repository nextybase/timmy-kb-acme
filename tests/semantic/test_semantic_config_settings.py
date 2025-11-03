# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from semantic.config import load_semantic_config

pytestmark = pytest.mark.semantic


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_semantic_config_merges_settings(tmp_path: Path) -> None:
    slug = "dummy"
    base_dir = tmp_path / "output" / f"timmy-kb-{slug}"
    base_dir.mkdir(parents=True, exist_ok=True)
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

    config_snapshot = config_yaml.read_text(encoding="utf-8")
    mapping_snapshot = mapping_yaml.read_text(encoding="utf-8")

    cfg = load_semantic_config(base_dir)
    assert cfg.top_k == 9
    assert cfg.score_min == 0.55
    assert "semantic_tagger" in cfg.mapping
    # Il loader non deve modificare i file esistenti
    assert config_yaml.read_text(encoding="utf-8") == config_snapshot
    assert mapping_yaml.read_text(encoding="utf-8") == mapping_snapshot
