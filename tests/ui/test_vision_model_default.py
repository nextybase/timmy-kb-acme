# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

import ui.config_store as config_store


def _setup_repo_config(tmp_path: Path, payload: dict) -> Path:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg_path = cfg_dir / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return cfg_path


def test_get_vision_model_falls_back_to_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = _setup_repo_config(tmp_path, {})
    monkeypatch.setattr(config_store, "CONFIG_DIR", cfg_path.parent)
    monkeypatch.setattr(config_store, "CONFIG_FILE", cfg_path)

    assert config_store.get_vision_model(default="my-default-model") == "my-default-model"


def test_get_vision_model_reads_value_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_payload = {"ai": {"vision": {"model": "gpt-4.1-mini-2025-04-14"}}}
    cfg_path = _setup_repo_config(tmp_path, cfg_payload)
    monkeypatch.setattr(config_store, "CONFIG_DIR", cfg_path.parent)
    monkeypatch.setattr(config_store, "CONFIG_FILE", cfg_path)

    assert config_store.get_vision_model() == "gpt-4.1-mini-2025-04-14"
