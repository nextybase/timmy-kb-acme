# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from ai.assistant_registry import _get_from_settings, _optional_env, resolve_prototimmy_config
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings


def test_get_from_settings_strict_rejects_non_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSettings:
        def get(self, path: str, default: object | None = None) -> object | None:
            return None

    # Il core ora accetta solo Settings tipizzato: sempre shape.invalid.
    with pytest.raises(ConfigError) as excinfo:
        _get_from_settings(FakeSettings(), "ai.prototimmy.model", default=None)
    assert excinfo.value.code == "config.shape.invalid"


def test_resolve_prototimmy_config_raises_when_model_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Config reale (SSoT) ma senza ai.prototimmy.model -> deve esplodere.
    repo_root = tmp_path / "repo-root"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    # cspell:ignore prototimm
    (repo_root / "config" / "config.yaml").write_text(
        "ai:\n  prototimmy:\n    assistant_id_env: PROTOTIMMY_ID\n    use_kb: true\n",
        encoding="utf-8",
    )
    settings = Settings.load(repo_root)
    monkeypatch.setenv("PROTOTIMMY_ID", "asst_dummy")

    with pytest.raises(ConfigError):
        resolve_prototimmy_config(settings)

    monkeypatch.delenv("PROTOTIMMY_ID", raising=False)


def test_assistant_registry_optional_env_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_ENV", raising=False)

    def _raise_key_error(name: str) -> str:
        raise KeyError(name)

    monkeypatch.setattr("ai.assistant_registry.env_utils.get_env_var", _raise_key_error)
    assert _optional_env("MISSING_ENV") is None


def test_assistant_registry_optional_env_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPTY_ENV", "  ")
    with pytest.raises(ConfigError) as excinfo:
        _optional_env("EMPTY_ENV")
    assert excinfo.value.code == "assistant.env.empty"


def test_assistant_registry_optional_env_read_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROKEN_ENV", "ok")

    def _raise_runtime_error(name: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("ai.assistant_registry.env_utils.get_env_var", _raise_runtime_error)
    with pytest.raises(ConfigError) as excinfo:
        _optional_env("BROKEN_ENV")
    assert excinfo.value.code == "assistant.env.read_failed"


# Nota: la copertura degli helper su Settings reali è già garantita dai boundary test dedicati.
