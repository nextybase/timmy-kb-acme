# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

import pipeline.env_utils as envu
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings

pytestmark = pytest.mark.settings


@pytest.fixture()
def sample_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        """
vision:
  engine: assistant
  model: gpt-4o-mini-2024-07-18
  assistant_id_env: DUMMY_ASSISTANT_ID
retriever:
  candidate_limit: 2000
  latency_budget_ms: 150
  auto_by_budget: true
ui:
  skip_preflight: false
gitbook_image: custom/honkit
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return config_path


def test_settings_loads_config(sample_config: Path) -> None:
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    data: Dict[str, object] = settings.as_dict()
    assert data["vision"]["model"] == "gpt-4o-mini-2024-07-18"
    assert settings.vision_model == "gpt-4o-mini-2024-07-18"
    assert settings.vision_engine == "assistant"
    assert settings.ui_skip_preflight is False


def test_resolve_env_ref_reads_env(sample_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUMMY_ASSISTANT_ID", "asst_dummy")
    envu._ENV_LOADED = False
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    resolved = settings.resolve_env_ref("vision.assistant_id_env", required=True)
    assert resolved == "asst_dummy"


def test_get_secret_reads_env(sample_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_dummy")
    envu._ENV_LOADED = False
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    secret = settings.get_secret("GITHUB_TOKEN", required=True)
    assert secret == "ghp_dummy"  # noqa: S105


def test_get_secret_missing_required_raises(sample_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_VAR", raising=False)
    envu._ENV_LOADED = False
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    with pytest.raises(ConfigError):
        settings.get_secret("MISSING_VAR", required=True)


def test_resolve_env_ref_missing_optional(sample_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    envu._ENV_LOADED = False
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    resolved = settings.resolve_env_ref("vision.assistant_id_env", required=False, default=None)
    assert resolved is None
