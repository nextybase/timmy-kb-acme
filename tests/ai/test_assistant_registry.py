# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

import ai.assistant_registry as assistant_registry
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings


def _write_settings(tmp_path: Path, payload: str) -> Settings:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True)
    cfg = repo_root / "config" / "config.yaml"
    cfg.write_text(payload, encoding="utf-8")
    return Settings.load(repo_root, config_path=cfg)


def _set_kgraph_assistant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KGRAPH_ASSISTANT_ID", "kgraph-assistant")


def test_prototimmy_config_uses_standard_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PROTOTIMMY_ID", "proto-asst")
    settings = _write_settings(
        tmp_path,
        "ai:\n  prototimmy:\n    model: proto-model\n",
    )
    cfg = assistant_registry.resolve_prototimmy_config(settings)
    assert cfg.assistant_env == "PROTOTIMMY_ID"
    assert cfg.assistant_id == "proto-asst"
    assert cfg.model == "proto-model"


def test_prototimmy_config_uses_custom_env_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUSTOM_ASSISTANT_ID", "custom-asst")
    settings = _write_settings(
        tmp_path,
        "ai:\n  prototimmy:\n    model: proto-model\n    assistant_id_env: CUSTOM_ASSISTANT_ID\n",
    )
    cfg = assistant_registry.resolve_prototimmy_config(settings)
    assert cfg.assistant_env == "CUSTOM_ASSISTANT_ID"
    assert cfg.assistant_id == "custom-asst"


def test_prototimmy_config_missing_env_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PROTOTIMMY_ID", raising=False)
    settings = _write_settings(
        tmp_path,
        "ai:\n  prototimmy:\n    model: proto-model\n",
    )
    with pytest.raises(ConfigError):
        assistant_registry.resolve_prototimmy_config(settings)


def test_assistant_id_empty_env_logs(monkeypatch, caplog):
    monkeypatch.setenv("MY_ASST", "")
    with pytest.raises(ConfigError) as excinfo:
        assistant_registry._resolve_assistant_id("MY_ASST", primary_env_name="MY_ASST")
    assert excinfo.value.code == "assistant.env.empty"


def test_resolve_kgraph_config_requires_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_kgraph_assistant(monkeypatch)
    settings = _write_settings(
        tmp_path,
        "ai:\n  kgraph:\n    model: nested-model\n",
    )
    cfg = assistant_registry.resolve_kgraph_config(settings)
    assert cfg.model == "nested-model"
