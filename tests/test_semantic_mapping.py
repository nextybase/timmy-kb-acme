from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from pipeline.exceptions import ConfigError
from semantic.semantic_mapping import load_semantic_mapping


@dataclass
class Ctx:
    config_dir: Optional[Path]
    repo_root_dir: Optional[Path]
    slug: Optional[str] = "s"


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_load_semantic_mapping_normalization_variants(tmp_path: Path) -> None:
    cfg = tmp_path / "client" / "config"
    # Mix of list, dict(keywords), dict(tags), and single string
    mapping_yaml = """
    Concept1: [" Foo ", "bar", "foo"]
    Concept2:
      keywords: ["x", "X", "y"]
    Concept3:
      keywords: ["e1", "e2", "e1"]
    Concept4:
      tags: ["t1", "t2", "t1", "t3"]
    Concept5: "solo"
    """
    write(cfg / "semantic_mapping.yaml", mapping_yaml)

    ctx = Ctx(config_dir=cfg, repo_root_dir=tmp_path)
    m = load_semantic_mapping(ctx)

    # Dedup case-insensitive, stripping spaces, preserve original casing of first occurrence
    assert m["Concept1"] == ["Foo", "bar"]
    assert m["Concept2"] == ["x", "y"]
    assert m["Concept3"] == ["e1", "e2"]
    assert m["Concept4"] == ["t1", "t2", "t3"]
    assert m["Concept5"] == ["solo"]


def test_load_semantic_mapping_missing_file_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "client" / "config"
    # no semantic_mapping.yaml
    ctx = Ctx(config_dir=cfg, repo_root_dir=tmp_path)
    with pytest.raises(ConfigError):
        _ = load_semantic_mapping(ctx)


def test_load_semantic_mapping_fallback_when_empty(tmp_path: Path) -> None:
    cfg = tmp_path / "client" / "config"
    repo_root = tmp_path / "repo"
    # Empty mapping triggers fallback
    write(cfg / "semantic_mapping.yaml", "{}\n")
    # Provide fallback under repo_root/config/default_semantic_mapping.yaml
    fallback_yaml = """
    Topic:
      keywords: ["alpha", "beta"]
    """
    write(repo_root / "config" / "default_semantic_mapping.yaml", fallback_yaml)

    ctx = Ctx(config_dir=cfg, repo_root_dir=repo_root)
    m = load_semantic_mapping(ctx)
    assert m == {"Topic": ["alpha", "beta"]}


def test_load_semantic_mapping_fallback_missing_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "client" / "config"
    repo_root = tmp_path / "repo"
    write(cfg / "semantic_mapping.yaml", "{}\n")  # forces fallback
    # No fallback provided
    ctx = Ctx(config_dir=cfg, repo_root_dir=repo_root)
    with pytest.raises(ConfigError):
        _ = load_semantic_mapping(ctx)
