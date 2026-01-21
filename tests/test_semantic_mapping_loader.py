# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pipeline.constants import SEMANTIC_MAPPING_FILE
from pipeline.exceptions import ConfigError
from semantic.mapping_loader import iter_mapping_candidates
from semantic.semantic_mapping import load_semantic_mapping


def _ctx(*, config_dir: Any, repo_root_dir: Any, slug: str = "dummy") -> Any:
    return SimpleNamespace(config_dir=config_dir, repo_root_dir=repo_root_dir, slug=slug)


def test_load_semantic_mapping_prefers_workspace(tmp_path):
    cfg = tmp_path / "cfg"
    repo = tmp_path / "repo"
    (cfg).mkdir()
    (repo / "semantic").mkdir(parents=True)
    (cfg / SEMANTIC_MAPPING_FILE).write_text("concept:\n  - tag-one\n", encoding="utf-8")

    mapping = load_semantic_mapping(_ctx(config_dir=cfg, repo_root_dir=repo))

    assert mapping == {"concept": ["tag-one"]}


def test_load_semantic_mapping_invalid_keywords_raises(tmp_path):
    repo = tmp_path / "repo"
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (repo / "semantic").mkdir(parents=True)
    (cfg / SEMANTIC_MAPPING_FILE).write_text("concept:\n  keywords:\n    - invalid\n", encoding="utf-8")
    ctx = _ctx(config_dir=cfg, repo_root_dir=repo)

    with pytest.raises(ConfigError):
        load_semantic_mapping(ctx)


def test_load_semantic_mapping_missing_raises(tmp_path):
    repo = tmp_path / "repo"
    (repo / "semantic").mkdir(parents=True)
    ctx = _ctx(config_dir=None, repo_root_dir=repo)

    with pytest.raises(ConfigError):
        load_semantic_mapping(ctx)


def test_iter_mapping_candidates_exposes_only_workspace(tmp_path):
    cfg = tmp_path / "cfg"
    repo = tmp_path / "repo"
    cfg.mkdir()
    repo.mkdir()

    candidates = list(
        iter_mapping_candidates(
            context_slug="dummy",
            config_dir=cfg,
            repo_root_dir=repo,
            repo_default_dir=None,
            mapping_filename=SEMANTIC_MAPPING_FILE,
        )
    )

    assert [source for source, _, _ in candidates] == ["workspace"]
