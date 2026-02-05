# SPDX-License-Identifier: GPL-3.0-or-later
# tests/semantic/test_export_tags_yaml.py
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import ConfigError
from semantic.api import export_tags_yaml_from_db


def _fake_write(*args, **kwargs):
    return Path(args[0]) / "tags_reviewed.yaml"


def _ensure_minimal_workspace(workspace: Path) -> None:
    """Costruisce la struttura workspace richiesta da WorkspaceLayout strict."""
    config_dir = workspace / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    for child in ("raw", "normalized", "semantic", "book", "logs"):
        (workspace / child).mkdir(parents=True, exist_ok=True)
    book_dir = workspace / "book"
    (book_dir / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("* [Dummy](README.md)\n", encoding="utf-8")


def test_export_tags_yaml_honors_workspace_base(tmp_path, monkeypatch):
    workspace = tmp_path / "output"
    semantic_dir = workspace / "semantic"
    semantic_dir.mkdir(parents=True)
    _ensure_minimal_workspace(workspace)
    db_path = semantic_dir / "tags.db"
    db_path.touch()

    monkeypatch.setattr("semantic.api._write_tags_yaml_from_db", _fake_write)

    result = export_tags_yaml_from_db(
        semantic_dir=semantic_dir,
        db_path=db_path,
        logger=SimpleNamespace(info=lambda *a, **k: None),
        workspace_base=workspace,
        slug="dummy",
        version="2",
    )

    assert result == semantic_dir / "tags_reviewed.yaml"


def test_export_tags_yaml_rejects_mismatched_db(tmp_path):
    workspace = tmp_path / "output"
    semantic_dir = workspace / "semantic"
    semantic_dir.mkdir(parents=True)
    _ensure_minimal_workspace(workspace)
    db_path = workspace / "external" / "tags.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.touch()

    with pytest.raises(ConfigError):
        export_tags_yaml_from_db(
            semantic_dir=semantic_dir,
            db_path=db_path,
            logger=SimpleNamespace(info=lambda *a, **k: None),
            workspace_base=workspace,
            slug="dummy",
        )
