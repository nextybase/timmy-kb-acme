# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore

from pipeline.exceptions import ConfigError
from tests._helpers.workspace_paths import local_workspace_dir, local_workspace_name
from ui import config_store


def _setup_repo_config(tmp_path: Path, payload: dict[str, Any]) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return config_path


class _StubContext:
    def __init__(self, config_path: Path, slug: str) -> None:
        self.config_path = config_path
        self.repo_root_dir = config_path.parent.parent
        self.slug = slug


def test_load_global_config_fails_if_missing(monkeypatch, tmp_path: Path):
    """
    Beta strict:
    se config/config.yaml manca, il runtime UI deve fermarsi.
    """
    fake_repo = tmp_path
    config_dir = fake_repo / "config"
    config_file = config_dir / "config.yaml"

    # Nessuna creazione automatica
    assert not config_file.exists()

    monkeypatch.setattr(config_store, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(config_store, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_store, "CONFIG_FILE", config_file)

    with pytest.raises(ConfigError):
        config_store._load_config()


def test_get_retriever_settings_prefers_client_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Repo config (global)
    repo_cfg = {
        "pipeline": {
            "retriever": {
                "auto_by_budget": False,
                "throttle": {
                    "candidate_limit": 8000,
                    "latency_budget_ms": 150,
                    "parallelism": 1,
                    "sleep_ms_between_calls": 0,
                },
            }
        }
    }
    repo_config_path = _setup_repo_config(tmp_path, repo_cfg)

    # Client config (specifico)
    client_config_path = local_workspace_dir(tmp_path / "output", "dummy") / "config" / "config.yaml"
    client_config_path.parent.mkdir(parents=True, exist_ok=True)
    client_cfg = {
        "pipeline": {
            "retriever": {
                "auto_by_budget": True,
                "throttle": {
                    "candidate_limit": 300,  # clamp -> MIN_CANDIDATE_LIMIT
                    "latency_budget_ms": 2500,  # clamp -> 2000
                    "parallelism": 4,
                    "sleep_ms_between_calls": 10,
                },
            }
        }
    }
    client_config_path.write_text(yaml.safe_dump(client_cfg, sort_keys=False), encoding="utf-8")

    # Strict: _load_config deve leggere SOLO da CONFIG_FILE; patchiamo anche REPO_ROOT per coerenza.
    monkeypatch.setattr(config_store, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(config_store, "CONFIG_DIR", repo_config_path.parent)
    monkeypatch.setattr(config_store, "CONFIG_FILE", repo_config_path)

    # Forziamo il contesto cliente a puntare al config client
    monkeypatch.setattr(
        config_store.ClientContext,
        "load",
        classmethod(lambda cls, **_: _StubContext(client_config_path, local_workspace_name("dummy"))),
    )

    limit, budget, auto = config_store.get_retriever_settings(slug="timmy-kb-dummy")

    assert limit == config_store.MIN_CANDIDATE_LIMIT
    assert budget == 2000
    assert auto is True


def test_load_repo_config_fails_if_missing(monkeypatch, tmp_path: Path):
    """
    Beta strict:
    se config/config.yaml repo-specific manca, errore esplicito.
    """
    repo_root = tmp_path
    config_dir = repo_root / "config"
    config_file = config_dir / "config.yaml"

    assert not config_file.exists()

    with pytest.raises(ConfigError):
        config_store._load_repo_config(repo_root)


def test_set_retriever_settings_updates_only_client_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Repo config (global) - deve restare invariata
    repo_cfg = {
        "pipeline": {
            "retriever": {
                "auto_by_budget": False,
                "throttle": {
                    "candidate_limit": 6000,
                    "latency_budget_ms": 100,
                    "parallelism": 1,
                    "sleep_ms_between_calls": 0,
                },
            }
        },
        "meta": {"version": 1},
    }
    repo_config_path = _setup_repo_config(tmp_path, repo_cfg)
    repo_original = repo_config_path.read_text(encoding="utf-8")

    # Client config: deve essere l'unico file modificato
    client_config_path = local_workspace_dir(tmp_path / "output", "dummy") / "config" / "config.yaml"
    client_config_path.parent.mkdir(parents=True, exist_ok=True)
    client_cfg = {
        "pipeline": {
            "retriever": {
                "auto_by_budget": False,
                "throttle": {
                    "candidate_limit": 500,
                    "latency_budget_ms": 50,
                    "parallelism": 2,
                    "sleep_ms_between_calls": 5,
                },
            }
        },
        "other": {"keep": "me"},
    }
    client_config_path.write_text(yaml.safe_dump(client_cfg, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(config_store, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(config_store, "CONFIG_DIR", repo_config_path.parent)
    monkeypatch.setattr(config_store, "CONFIG_FILE", repo_config_path)

    monkeypatch.setattr(
        config_store.ClientContext,
        "load",
        classmethod(lambda cls, **_: _StubContext(client_config_path, local_workspace_name("dummy"))),
    )

    config_store.set_retriever_settings(1234, 1800, True, slug="timmy-kb-dummy")

    updated_client = yaml.safe_load(client_config_path.read_text(encoding="utf-8"))
    assert updated_client["pipeline"]["retriever"] == {
        "auto_by_budget": True,
        "throttle": {
            "candidate_limit": 1234,
            "latency_budget_ms": 1800,
            "parallelism": 2,
            "sleep_ms_between_calls": 5,
        },
    }
    assert updated_client["other"] == {"keep": "me"}
    assert repo_config_path.read_text(encoding="utf-8") == repo_original


def test_load_client_config_fails_on_unserializable_settings(monkeypatch, tmp_path: Path):
    """
    Beta strict:
    se le settings cliente non sono convertibili in dict,
    non si deve tornare {} in silenzio.
    """

    class BrokenSettings:
        pass

    def _broken_loader(*_args, **_kwargs):
        return BrokenSettings()

    monkeypatch.setattr(config_store, "load_client_settings", _broken_loader)

    ctx_dir = tmp_path / "client"
    ctx_dir.mkdir()

    monkeypatch.setattr(
        config_store,
        "get_client_context",
        lambda slug: type("Ctx", (), {"repo_root": ctx_dir}),
    )

    with pytest.raises(ConfigError):
        config_store._load_client_config("dummy-client")
