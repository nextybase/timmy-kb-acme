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
meta:
  client_name: "Cliente Demo"
ui:
  skip_preflight: false
  allow_local_only: false
  admin_local_mode: true
ai:
  openai:
    timeout: 60
    max_retries: 4
    http2_enabled: true
  prototimmy:
    engine: assistants
    model: gpt-4.1
    assistant_id_env: DUMMY_PROTOTIMMY_ID
    use_kb: true
  planner_assistant:
    engine: assistants
    model: gpt-4.1
    assistant_id_env: DUMMY_PLANNER_ID
    use_kb: true
  ocp_executor:
    engine: assistants
    model: gpt-4.1
    assistant_id_env: DUMMY_OCP_ID
    use_kb: true
  kgraph:
    engine: assistants
    model: gpt-4.1
    assistant_id_env: DUMMY_KGRAPH_ID
    use_kb: true
  vision:
    engine: responses
    model: gpt-4o-mini-2024-07-18
    assistant_id_env: DUMMY_ASSISTANT_ID
    snapshot_retention_days: 45
    strict_output: true
pipeline:
  retriever:
    auto_by_budget: true
    throttle:
      candidate_limit: 2000
      latency_budget_ms: 150
      parallelism: 2
      sleep_ms_between_calls: 25
ops:
  log_level: DEBUG
finance:
  import_enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return config_path


def test_settings_loads_config(sample_config: Path) -> None:
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    data: Dict[str, object] = settings.as_dict()
    assert data["ai"]["vision"]["model"] == "gpt-4o-mini-2024-07-18"
    assert "prototimmy" in data["ai"] and data["ai"]["prototimmy"]["model"] == "gpt-4.1"
    assert "planner_assistant" in data["ai"] and data["ai"]["planner_assistant"]["model"] == "gpt-4.1"
    assert "ocp_executor" in data["ai"] and data["ai"]["ocp_executor"]["model"] == "gpt-4.1"
    assert "kgraph" in data["ai"] and data["ai"]["kgraph"]["model"] == "gpt-4.1"
    assert settings.client_name == "Cliente Demo"
    assert settings.vision_model == "gpt-4o-mini-2024-07-18"
    assert settings.vision_engine == "responses"
    assert settings.vision_snapshot_retention_days == 45
    assert settings.ui_skip_preflight is False
    assert settings.ui_allow_local_only is False
    assert settings.ui_admin_local_mode is True
    assert settings.openai_settings.timeout == 60
    assert settings.openai_settings.max_retries == 4
    assert settings.openai_settings.http2_enabled is True
    assert settings.retriever_throttle.candidate_limit == 2000
    assert settings.retriever_throttle.parallelism == 2
    assert settings.ops_log_level == "DEBUG"
    assert settings.finance_import_enabled is True


def test_resolve_env_ref_reads_env(sample_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUMMY_ASSISTANT_ID", "asst_dummy")  # pragma: allowlist secret
    envu._ENV_LOADED = False
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    resolved = settings.resolve_env_ref("ai.vision.assistant_id_env", required=True)
    assert resolved == "asst_dummy"


def test_get_secret_reads_env(sample_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_ACCOUNT_FILE", "dummy.json")  # noqa: S105  # pragma: allowlist secret
    envu._ENV_LOADED = False
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    secret = settings.get_secret("SERVICE_ACCOUNT_FILE", required=True)
    assert secret == "dummy.json"  # noqa: S105  # pragma: allowlist secret


def test_get_secret_missing_required_raises(sample_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_VAR", raising=False)
    envu._ENV_LOADED = False
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    with pytest.raises(ConfigError):
        settings.get_secret("MISSING_VAR", required=True)


def test_resolve_env_ref_missing_optional(sample_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    envu._ENV_LOADED = False
    settings = Settings.load(sample_config.parent.parent, config_path=sample_config)
    resolved = settings.resolve_env_ref("ai.vision.assistant_id_env", required=False, default=None)
    assert resolved is None
