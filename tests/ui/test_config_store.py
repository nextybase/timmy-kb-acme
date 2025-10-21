from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

import ui.config_store as config_store
from pipeline.exceptions import ConfigError


def _setup_repo_config(tmp_path: Path, payload: Dict[str, Any]) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return config_path


class _StubContext:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path


def test_get_retriever_settings_prefers_client_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_cfg = {
        "retriever": {
            "candidate_limit": 8000,
            "latency_budget_ms": 150,
            "auto_by_budget": False,
        }
    }
    repo_config_path = _setup_repo_config(tmp_path, repo_cfg)

    client_config_path = tmp_path / "output" / "timmy-kb-dummy" / "config" / "config.yaml"
    client_config_path.parent.mkdir(parents=True)
    client_cfg = {
        "retriever": {
            "candidate_limit": 300,  # clamp -> MIN_CANDIDATE_LIMIT
            "latency_budget_ms": 2500,  # clamp -> 2000
            "auto_by_budget": True,
        }
    }
    client_config_path.write_text(yaml.safe_dump(client_cfg, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(config_store, "CONFIG_DIR", repo_config_path.parent)
    monkeypatch.setattr(config_store, "CONFIG_FILE", repo_config_path)
    monkeypatch.setattr(
        config_store.ClientContext,
        "load",
        classmethod(lambda cls, **_: _StubContext(client_config_path)),
    )

    limit, budget, auto = config_store.get_retriever_settings(slug="timmy-kb-dummy")

    assert limit == config_store.MIN_CANDIDATE_LIMIT
    assert budget == 2000
    assert auto is True


def test_set_retriever_settings_updates_only_client_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_cfg = {
        "retriever": {
            "candidate_limit": 6000,
            "latency_budget_ms": 100,
            "auto_by_budget": False,
        },
        "meta": {"version": 1},
    }
    repo_config_path = _setup_repo_config(tmp_path, repo_cfg)
    repo_original = repo_config_path.read_text(encoding="utf-8")

    client_config_path = tmp_path / "output" / "timmy-kb-dummy" / "config" / "config.yaml"
    client_config_path.parent.mkdir(parents=True)
    client_cfg = {
        "retriever": {
            "candidate_limit": 500,
            "latency_budget_ms": 50,
            "auto_by_budget": False,
        },
        "other": {"keep": "me"},
    }
    client_config_path.write_text(yaml.safe_dump(client_cfg, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(config_store, "CONFIG_DIR", repo_config_path.parent)
    monkeypatch.setattr(config_store, "CONFIG_FILE", repo_config_path)
    monkeypatch.setattr(
        config_store.ClientContext,
        "load",
        classmethod(lambda cls, **_: _StubContext(client_config_path)),
    )

    config_store.set_retriever_settings(1234, 1800, True, slug="timmy-kb-dummy")

    updated_client = yaml.safe_load(client_config_path.read_text(encoding="utf-8"))
    assert updated_client["retriever"] == {
        "candidate_limit": 1234,
        "latency_budget_ms": 1800,
        "budget_ms": 1800,
        "auto_by_budget": True,
        "auto": True,
    }
    assert updated_client["other"] == {"keep": "me"}
    assert repo_config_path.read_text(encoding="utf-8") == repo_original


def test_get_retriever_settings_fallback_on_configerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    repo_cfg = {
        "retriever": {
            "candidate_limit": 250,  # clamp -> MIN_CANDIDATE_LIMIT
            "latency_budget_ms": -5,  # clamp -> 0
            "auto_by_budget": False,
        }
    }
    repo_config_path = _setup_repo_config(tmp_path, repo_cfg)

    monkeypatch.setattr(config_store, "CONFIG_DIR", repo_config_path.parent)
    monkeypatch.setattr(config_store, "CONFIG_FILE", repo_config_path)

    def _boom(**_: Any) -> _StubContext:
        raise ConfigError("ctx failure")

    monkeypatch.setattr(config_store.ClientContext, "load", classmethod(_boom))

    caplog.set_level("DEBUG", logger="ui.config_store")

    limit, budget, auto = config_store.get_retriever_settings(slug="timmy-kb-dummy")

    assert limit == config_store.MIN_CANDIDATE_LIMIT
    assert budget == 0
    assert auto is False
    assert any("client_fallback" in record.message for record in caplog.records)
