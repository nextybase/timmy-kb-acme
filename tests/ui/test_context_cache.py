# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ui.utils import context_cache as cache


class _StubClientContext:
    def __init__(self, slug: str, require_drive_env: bool, run_id: str | None = None) -> None:
        self.slug = slug
        self.require_drive_env = require_drive_env
        self.run_id = run_id

    @classmethod
    def load(cls, **kwargs: Any) -> "_StubClientContext":
        return cls(
            str(kwargs["slug"]),
            bool(kwargs.get("require_drive_env", False)),
            kwargs.get("run_id"),
        )


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola lo state interno tra i test (session_state + ClientContext stub)."""
    monkeypatch.setattr(cache, "st", SimpleNamespace(session_state={}))
    monkeypatch.setattr(cache, "ClientContext", _StubClientContext)


def test_get_client_context_reuses_session(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    class _CountingClientContext:
        def __init__(self, slug: str, require_drive_env: bool, run_id: str | None = None) -> None:
            self.slug = slug
            self.require_drive_env = require_drive_env
            self.run_id = run_id

        @classmethod
        def load(cls, **kwargs: Any) -> "_CountingClientContext":
            calls.append(
                (
                    str(kwargs["slug"]),
                    bool(kwargs.get("require_drive_env", False)),
                    kwargs.get("run_id"),
                )
            )
            return cls(
                kwargs["slug"],
                bool(kwargs.get("require_drive_env", False)),
                kwargs.get("run_id"),
            )

    monkeypatch.setattr(cache, "ClientContext", _CountingClientContext)
    cache.st.session_state.clear()
    calls.clear()

    cache.get_client_context("Dummy-Slug", require_drive_env=False)
    cache.get_client_context("dummy-slug", require_drive_env=False)
    assert calls == [("Dummy-Slug", False, None)]

    cache.get_client_context("dummy-slug", require_drive_env=True)
    assert calls[-1] == ("dummy-slug", True, None)

    cache.invalidate_client_context("dummy-slug")
    cache.get_client_context("dummy-slug", require_drive_env=False)
    assert len(calls) == 3


def test_get_client_context_force_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    loads: list[str] = []

    class _CountingClientContext:
        def __init__(self, slug: str, require_drive_env: bool, run_id: str | None = None) -> None:
            self.slug = slug
            self.require_drive_env = require_drive_env
            self.run_id = run_id

        @classmethod
        def load(cls, **kwargs: Any) -> "_CountingClientContext":
            loads.append(str(kwargs["slug"]))
            return cls(kwargs["slug"], False, kwargs.get("run_id"))

    monkeypatch.setattr(cache, "ClientContext", _CountingClientContext)
    cache.st.session_state.clear()
    loads.clear()

    first = cache.get_client_context("tmp", require_drive_env=False)
    forced = cache.get_client_context("tmp", require_drive_env=False, force_reload=True)
    assert first is not forced
    assert len(loads) == 2
    cache.get_client_context("tmp", require_drive_env=False)
    assert len(loads) == 2


def test_invalidate_and_force_reload_refreshes_context(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StaleContext:
        def __init__(self, slug: str) -> None:
            self.slug = slug
            self.repo_root_dir = None

        @classmethod
        def load(cls, **kwargs: Any) -> "_StaleContext":
            return cls(str(kwargs["slug"]))

    class _FreshContext:
        def __init__(self, slug: str) -> None:
            self.slug = slug
            self.repo_root_dir = "base"

        @classmethod
        def load(cls, **kwargs: Any) -> "_FreshContext":
            return cls(str(kwargs["slug"]))

    monkeypatch.setattr(cache, "ClientContext", _StaleContext)
    cache.st.session_state.clear()
    first = cache.get_client_context("slug", require_drive_env=False)
    assert first.repo_root_dir is None

    monkeypatch.setattr(cache, "ClientContext", _FreshContext)
    cache.invalidate_client_context("slug")
    refreshed = cache.get_client_context("slug", require_drive_env=False, force_reload=True)
    assert refreshed is not first
    assert refreshed.repo_root_dir == "base"


def test_get_client_context_tracks_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    loads: list[str | None] = []

    class _RunAwareClientContext:
        def __init__(self, slug: str, require_drive_env: bool, run_id: str | None = None) -> None:
            self.slug = slug
            self.require_drive_env = require_drive_env
            self.run_id = run_id

        @classmethod
        def load(cls, **kwargs: Any) -> "_RunAwareClientContext":
            loads.append(kwargs.get("run_id"))
            return cls(kwargs["slug"], bool(kwargs.get("require_drive_env", False)), kwargs.get("run_id"))

    monkeypatch.setattr(cache, "ClientContext", _RunAwareClientContext)
    cache.st.session_state.clear()
    loads.clear()

    first = cache.get_client_context("slug", require_drive_env=False, run_id="run-a")
    again = cache.get_client_context("slug", require_drive_env=False, run_id="run-a")
    second_run = cache.get_client_context("slug", require_drive_env=False, run_id="run-b")

    assert first is again
    assert second_run is not first
    assert second_run.run_id == "run-b"
    assert loads == ["run-a", "run-b"]

    default_ctx = cache.get_client_context("slug", require_drive_env=False)
    assert default_ctx.run_id is None
    # Nessun load aggiuntivo per la chiamata precedente con run_id="run-b"
    assert loads == ["run-a", "run-b", None]
