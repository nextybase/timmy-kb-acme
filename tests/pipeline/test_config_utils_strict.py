# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import pipeline.config_utils as config_utils
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError


def test_refresh_context_settings_logs_on_failure(monkeypatch: pytest.MonkeyPatch, caplog, tmp_path: Path) -> None:
    ctx = ClientContext(
        slug="dummy",
        repo_root_dir=tmp_path,
        config_path=tmp_path / "config" / "config.yaml",
    )

    def _boom(*_a: object, **_k: object):
        raise RuntimeError("load failed")

    monkeypatch.setattr(config_utils.ContextSettings, "load", _boom)
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")

    caplog.set_level(logging.WARNING, logger="pipeline.config_utils")

    # Non deve essere fatal (write già avvenuta), ma deve essere osservabile.
    config_utils._refresh_context_settings(ctx)

    rec = next(
        (r for r in caplog.records if r.getMessage() == "pipeline.config_utils.context_settings_refresh_failed"),
        None,
    )
    assert rec is not None
    assert getattr(rec, "slug", None) == "dummy"


def test_refresh_context_settings_strict_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = ClientContext(
        slug="dummy",
        repo_root_dir=tmp_path,
        config_path=tmp_path / "config" / "config.yaml",
    )

    def _boom(*_a: object, **_k: object):
        raise RuntimeError("load failed")

    monkeypatch.setattr(config_utils.ContextSettings, "load", _boom)
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")

    with pytest.raises(ConfigError):
        config_utils._refresh_context_settings(ctx)


def test_load_client_settings_raises_on_non_convertibile_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Oggetto non convertibile: vars() solleva TypeError se non ha __dict__ (slots vuoti).
    class _SlotsSettings:
        __slots__ = ()

    def _fake_load(*_a: object, **_k: object):
        return _SlotsSettings()

    monkeypatch.setattr(config_utils.ContextSettings, "load", _fake_load)

    ctx = ClientContext(
        slug="dummy",
        repo_root_dir=tmp_path,
        config_path=tmp_path / "config" / "config.yaml",
    )

    with pytest.raises(ConfigError):
        config_utils.load_client_settings(ctx, reload=True)
