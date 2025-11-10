# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ui.utils import context_cache as cache


class _StubClientContext:
    def __init__(self, slug: str, require_env: bool) -> None:
        self.slug = slug
        self.require_env = require_env

    @classmethod
    def load(cls, **kwargs: Any) -> "_StubClientContext":
        return cls(str(kwargs["slug"]), bool(kwargs.get("require_env", False)))


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola lo state interno tra i test (session_state + ClientContext stub)."""
    monkeypatch.setattr(cache, "st", SimpleNamespace(session_state={}))
    monkeypatch.setattr(cache, "ClientContext", _StubClientContext)


def test_get_client_context_reuses_session(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    class _CountingClientContext:
        def __init__(self, slug: str, require_env: bool) -> None:
            self.slug = slug
            self.require_env = require_env

        @classmethod
        def load(cls, **kwargs: Any) -> "_CountingClientContext":
            calls.append((str(kwargs["slug"]), bool(kwargs.get("require_env", False))))
            return cls(kwargs["slug"], bool(kwargs.get("require_env", False)))

    monkeypatch.setattr(cache, "ClientContext", _CountingClientContext)
    cache.st.session_state.clear()
    calls.clear()

    cache.get_client_context("Demo-Slug", require_env=False)
    cache.get_client_context("demo-slug", require_env=False)
    assert calls == [("Demo-Slug", False)]

    cache.get_client_context("demo-slug", require_env=True)
    assert calls[-1] == ("demo-slug", True)

    cache.invalidate_client_context("demo-slug")
    cache.get_client_context("demo-slug", require_env=False)
    assert len(calls) == 3


def test_get_client_context_force_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    loads: list[str] = []

    class _CountingClientContext:
        def __init__(self, slug: str, require_env: bool) -> None:
            self.slug = slug
            self.require_env = require_env

        @classmethod
        def load(cls, **kwargs: Any) -> "_CountingClientContext":
            loads.append(str(kwargs["slug"]))
            return cls(kwargs["slug"], False)

    monkeypatch.setattr(cache, "ClientContext", _CountingClientContext)
    cache.st.session_state.clear()
    loads.clear()

    first = cache.get_client_context("tmp", require_env=False)
    forced = cache.get_client_context("tmp", require_env=False, force_reload=True)
    assert first is not forced
    assert len(loads) == 2
    cache.get_client_context("tmp", require_env=False)
    assert len(loads) == 2
