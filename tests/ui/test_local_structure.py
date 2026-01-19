# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.workspace_bootstrap import bootstrap_client_workspace
from ui.services.local_structure import materialize_local_raw_from_cartelle


def _prepare_workspace(tmp_path: Path, slug: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace_root = tmp_path / f"timmy-kb-{slug}"
    monkeypatch.setenv("REPO_ROOT_DIR", str(workspace_root))
    ctx = ClientContext.load(slug=slug, require_env=False, repo_root_dir=workspace_root)
    bootstrap_client_workspace(ctx)
    return workspace_root


def test_local_structure_creates_raw_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "local-raw-ok"
    workspace_root = _prepare_workspace(tmp_path, slug, monkeypatch)
    cartelle = workspace_root / "semantic" / "cartelle_raw.yaml"
    cartelle.write_text(
        "version: 1\nfolders:\n  - key: governance\n    title: Governance\n",
        encoding="utf-8",
    )

    materialize_local_raw_from_cartelle(slug=slug, require_env=False)

    assert (workspace_root / "raw" / "governance").exists()


def test_local_structure_rejects_legacy_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "local-raw-legacy"
    workspace_root = _prepare_workspace(tmp_path, slug, monkeypatch)
    cartelle = workspace_root / "semantic" / "cartelle_raw.yaml"
    cartelle.write_text("raw:\n  governance: {}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="legacy 'raw'"):
        materialize_local_raw_from_cartelle(slug=slug, require_env=False)


def test_local_structure_rejects_empty_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "local-raw-empty"
    workspace_root = _prepare_workspace(tmp_path, slug, monkeypatch)
    cartelle = workspace_root / "semantic" / "cartelle_raw.yaml"
    cartelle.write_text("version: 1\nfolders: []\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="non puo' essere vuoto"):
        materialize_local_raw_from_cartelle(slug=slug, require_env=False)
