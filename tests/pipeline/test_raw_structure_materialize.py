# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline import vision_runner
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.vision_runner import materialize_raw_structure


def _write_text(base: Path, target: Path, text: str) -> Path:
    safe_path = ensure_within_and_resolve(base, target)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(safe_path, text, encoding="utf-8", atomic=True)
    return safe_path


def _setup_workspace(tmp_path: Path, slug: str, mapping_text: str) -> Path:
    base = tmp_path / "workspace"
    base.mkdir(parents=True, exist_ok=True)
    for name in ("raw", "normalized", "semantic", "logs", "book", "config"):
        (base / name).mkdir(parents=True, exist_ok=True)
    _write_text(base, base / "config" / "config.yaml", "client_name: Test\n")
    _write_text(base, base / "book" / "README.md", "# Test\n")
    _write_text(base, base / "book" / "SUMMARY.md", "* [Intro](intro.md)\n")
    _write_text(base, base / "semantic" / "semantic_mapping.yaml", mapping_text)
    return base


def _logger() -> logging.Logger:
    log = logging.getLogger("test.raw_structure")
    log.setLevel(logging.INFO)
    if not log.handlers:
        log.addHandler(logging.NullHandler())
    return log


class _Ctx:
    def __init__(self, repo_root_dir: Path) -> None:
        self.repo_root_dir = repo_root_dir
        self.settings = {}


def test_materialize_raw_structure_creates_local_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _setup_workspace(tmp_path, "acme", "areas:\n  - key: A\n  - key: B\n")
    ctx = _Ctx(base)
    monkeypatch.setattr(
        vision_runner,
        "get_client_config",
        lambda _ctx: {"integrations": {"drive": {"raw_folder_id": "raw-id"}}},
        raising=True,
    )
    monkeypatch.setattr(
        vision_runner,
        "create_drive_structure_from_names",
        lambda **kwargs: list(kwargs.get("folder_names") or []),
        raising=True,
    )

    result = materialize_raw_structure(ctx, _logger(), repo_root_dir=base, slug="acme")

    assert (base / "raw" / "a").is_dir()
    assert (base / "raw" / "b").is_dir()
    assert result.get("drive_status") == "created"


def test_materialize_raw_structure_missing_areas_raises(tmp_path: Path) -> None:
    base = _setup_workspace(tmp_path, "acme", "version: 1\n")
    ctx = _Ctx(base)

    with pytest.raises(ConfigError) as excinfo:
        materialize_raw_structure(ctx, _logger(), repo_root_dir=base, slug="acme")

    assert "areas" in str(excinfo.value).lower()


def test_materialize_raw_structure_idempotent(tmp_path: Path) -> None:
    base = _setup_workspace(tmp_path, "acme", "areas:\n  - key: Area One\n  - key: Area Two\n")
    ctx = _Ctx(base)

    def _get_client_config(_ctx: object) -> dict[str, object]:
        return {"integrations": {"drive": {"raw_folder_id": "raw-id"}}}

    def _create_drive_structure_from_names(**kwargs: object) -> list[str]:
        return list(kwargs.get("folder_names") or [])

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(vision_runner, "get_client_config", _get_client_config, raising=True)
    monkeypatch.setattr(
        vision_runner, "create_drive_structure_from_names", _create_drive_structure_from_names, raising=True
    )
    try:
        materialize_raw_structure(ctx, _logger(), repo_root_dir=base, slug="acme")
        materialize_raw_structure(ctx, _logger(), repo_root_dir=base, slug="acme")
    finally:
        monkeypatch.undo()

    assert (base / "raw" / "area-one").is_dir()
    assert (base / "raw" / "area-two").is_dir()
