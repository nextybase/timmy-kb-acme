# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json

import pytest

from pipeline.exceptions import ConfigError
from pipeline.oidc_utils import ensure_oidc_context, fetch_github_id_token


def _settings(payload: dict) -> dict:
    return {"security": {"oidc": payload}}


def test_oidc_disabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("ACTIONS_ID_TOKEN_REQUEST_URL", raising=False)
    monkeypatch.delenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", raising=False)
    ctx = ensure_oidc_context(_settings({"enabled": False}))
    assert ctx["enabled"] is False


def test_oidc_enabled_missing_audience_name_raises() -> None:
    with pytest.raises(ConfigError) as excinfo:
        ensure_oidc_context(_settings({"enabled": True, "provider": "github", "audience_env": ""}))
    assert "missing_keys=[" in str(excinfo.value)
    assert "security.oidc.audience_env" in str(excinfo.value)


def test_oidc_enabled_missing_required_envs_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("ACTIONS_ID_TOKEN_REQUEST_URL", raising=False)
    monkeypatch.delenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", raising=False)
    with pytest.raises(ConfigError) as excinfo:
        ensure_oidc_context(_settings({"enabled": True, "provider": "github", "audience_env": "OIDC_AUDIENCE"}))
    message = str(excinfo.value)
    assert "missing_keys=[" in message
    assert "OIDC_AUDIENCE" in message
    assert "ACTIONS_ID_TOKEN_REQUEST_URL" in message
    assert "ACTIONS_ID_TOKEN_REQUEST_TOKEN" in message


def test_oidc_enabled_unsupported_provider_raises() -> None:
    with pytest.raises(ConfigError) as excinfo:
        ensure_oidc_context(_settings({"enabled": True, "provider": "vault", "audience_env": "OIDC_AUDIENCE"}))
    assert "provider" in str(excinfo.value)


def test_oidc_token_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_AUDIENCE", "aud")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://example.com/oidc")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "token")
    monkeypatch.setattr("pipeline.oidc_utils.fetch_github_id_token", lambda *_a, **_k: None)
    with pytest.raises(ConfigError) as excinfo:
        ensure_oidc_context(_settings({"enabled": True, "provider": "github", "audience_env": "OIDC_AUDIENCE"}))
    assert "token acquisition failed" in str(excinfo.value)


def test_fetch_github_id_token_retries_once_without_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://example.com/oidc")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "token")
    calls = {"n": 0}

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
            return False

        def read(self) -> bytes:
            return self._body

    def _urlopen(_request, timeout=10):  # type: ignore[no-untyped-def]
        _ = timeout
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return _Resp(json.dumps({"value": "tok"}).encode("utf-8"))

    monkeypatch.setattr("pipeline.oidc_utils.urllib.request.urlopen", _urlopen)
    fetched_id_token = fetch_github_id_token("aud")
    assert isinstance(fetched_id_token, str)
    assert len(fetched_id_token) == 3
    assert calls["n"] == 2
