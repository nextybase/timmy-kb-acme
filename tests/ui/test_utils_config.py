# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from ui.utils.config import DriveEnvConfig, TagsEnvConfig, get_drive_env_config, get_tags_env_config


def test_get_drive_env_config_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.delenv("DRIVE_ID", raising=False)
    monkeypatch.delenv("DRIVE_PARENT_FOLDER_ID", raising=False)

    cfg = get_drive_env_config()

    assert isinstance(cfg, DriveEnvConfig)
    assert cfg.service_account_file is None
    assert cfg.drive_id is None
    assert cfg.parent_folder_id is None
    assert cfg.service_account_ok is False
    assert cfg.drive_id_ok is False
    assert cfg.download_ready is False


def test_get_drive_env_config_with_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saf = tmp_path / "service.json"
    saf.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SERVICE_ACCOUNT_FILE", str(saf))
    monkeypatch.setenv("DRIVE_ID", "drive-123")
    monkeypatch.setenv("DRIVE_PARENT_FOLDER_ID", "parent-456")

    cfg = get_drive_env_config()

    assert cfg.service_account_file == str(saf)
    assert cfg.drive_id == "drive-123"
    assert cfg.parent_folder_id == "parent-456"
    assert cfg.service_account_ok is True
    assert cfg.drive_id_ok is True
    assert cfg.download_ready is True


def test_get_tags_env_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAGS_MODE", raising=False)
    cfg_default = get_tags_env_config()
    assert isinstance(cfg_default, TagsEnvConfig)
    assert cfg_default.raw_value == ""
    assert cfg_default.normalized == ""
    assert cfg_default.is_stub is False

    monkeypatch.setenv("TAGS_MODE", "stub")
    cfg_stub = get_tags_env_config()
    assert cfg_stub.raw_value == "stub"
    assert cfg_stub.normalized == "stub"
    assert cfg_stub.is_stub is True

    monkeypatch.setenv("TAGS_MODE", "SpAcY")
    cfg_other = get_tags_env_config()
    assert cfg_other.raw_value == "SpAcY"
    assert cfg_other.normalized == "spacy"
    assert cfg_other.is_stub is False
