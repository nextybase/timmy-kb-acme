# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline import github_env_flags as flags


class _Ctx(SimpleNamespace):
    pass


def test_should_push_respects_context_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _Ctx(env={"TIMMY_NO_GITHUB": "true"})
    assert flags.should_push(ctx) is False


def test_should_push_respects_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKIP_GITHUB_PUSH", raising=False)
    ctx = _Ctx(env={})
    assert flags.should_push(ctx) is True
    monkeypatch.setenv("SKIP_GITHUB_PUSH", "1")
    assert flags.should_push(ctx) is False


def test_get_force_allowed_branches_merges_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _Ctx(env={"GIT_FORCE_ALLOWED_BRANCHES": ["feature/*", "release"]})
    assert flags.get_force_allowed_branches(ctx) == ["feature/*", "release"]
    ctx = _Ctx(env={})
    monkeypatch.setenv("GIT_FORCE_ALLOWED_BRANCHES", "hotfix/*, main")
    assert flags.get_force_allowed_branches(ctx) == ["hotfix/*", "main"]


def test_is_branch_allowed_for_force_patterns() -> None:
    ctx = _Ctx(env={"GIT_FORCE_ALLOWED_BRANCHES": ["main", "release/*"]})
    assert flags.is_branch_allowed_for_force("main", ctx) is True
    assert flags.is_branch_allowed_for_force("release/1.0", ctx) is True
    assert flags.is_branch_allowed_for_force("feature/x", ctx, allow_if_unset=False) is False
