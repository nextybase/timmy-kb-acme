# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.paths import workspace_paths
from tools.dummy.orchestrator import validate_dummy_structure


@pytest.fixture
def logger() -> logging.Logger:
    log = logging.getLogger("test.dummy.hardcheck")
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.INFO)
    return log


def _write_required_dummy_files(workspace_root: Path) -> None:
    (workspace_root / "config").mkdir(parents=True, exist_ok=True)
    (workspace_root / "semantic").mkdir(parents=True, exist_ok=True)
    (workspace_root / "book").mkdir(parents=True, exist_ok=True)
    (workspace_root / "raw").mkdir(parents=True, exist_ok=True)

    (workspace_root / "config" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (workspace_root / "semantic" / "semantic_mapping.yaml").write_text("context: {}\n", encoding="utf-8")
    (workspace_root / "semantic" / "tags.db").write_bytes(b"")
    (workspace_root / "book" / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (workspace_root / "book" / "SUMMARY.md").write_text("* [Dummy](README.md)\n", encoding="utf-8")
    (workspace_root / "raw" / "sample.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")


def test_dummy_validate_structure_passes_when_cartelle_yaml_present(tmp_path: Path, logger: logging.Logger) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-hc"
    layout = workspace_paths(slug, repo_root=repo_root, create=True)

    _write_required_dummy_files(layout.workspace_root)
    (layout.semantic_dir / "cartelle_raw.yaml").write_text("folders: []\n", encoding="utf-8")

    validate_dummy_structure(layout.workspace_root, logger)


def test_dummy_validate_structure_fails_when_cartelle_yaml_missing(tmp_path: Path, logger: logging.Logger) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-hc"
    layout = workspace_paths(slug, repo_root=repo_root, create=True)

    _write_required_dummy_files(layout.workspace_root)

    with pytest.raises(RuntimeError) as exc:
        validate_dummy_structure(layout.workspace_root, logger)
    assert "cartelle_raw" in str(exc.value)
