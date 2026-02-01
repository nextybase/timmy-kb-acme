# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve
from ui import config_store


def _write_cfg(repo_root: Path, payload: str) -> None:
    cfg_dir = repo_root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = ensure_within_and_resolve(cfg_dir, cfg_dir / "config.yaml")
    safe_write_text(cfg_path, payload, encoding="utf-8", atomic=True)


def test_get_skip_preflight_reads_ui_key(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_cfg(repo_root, "ui:\n  skip_preflight: true\n")
    assert config_store.get_skip_preflight(repo_root=repo_root) is True


def test_get_skip_preflight_defaults_false(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_cfg(repo_root, "ui:\n  skip_preflight: false\n")
    assert config_store.get_skip_preflight(repo_root=repo_root) is False
