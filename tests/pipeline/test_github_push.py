# SPDX-License-Identifier: GPL-3.0-only
"""Test per la pipeline GitHub refactorata (push orchestrator)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from pipeline import github_utils
from pipeline.exceptions import ForcePushError, PushError


@dataclass
class _DummyContext:
    slug: str
    md_dir: Path
    base_dir: Path
    env: dict[str, Any]


def _make_context(tmp_path: Path) -> _DummyContext:
    base_dir = tmp_path / "workspace"
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "foo.md").write_text("# demo", encoding="utf-8")
    return _DummyContext(slug="demo", md_dir=book_dir, base_dir=base_dir, env={})


def test_push_output_to_github_skips_when_no_markdown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "workspace"
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    ctx = _DummyContext(slug="demo", md_dir=book_dir, base_dir=base_dir, env={})

    def _fail_prepare(*_: Any, **__: Any) -> None:
        raise AssertionError("prepare_repo non dovrebbe essere invocato")

    monkeypatch.setattr(github_utils, "_prepare_repo", _fail_prepare)

    github_utils.push_output_to_github(
        ctx,
        github_token="token123",  # noqa: S106 - token fittizio per test
        do_push=True,
    )


def test_push_output_to_github_success_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _make_context(tmp_path)
    calls: list[tuple[str, Any]] = []
    stages: list[str] = []

    tmp_dir = ctx.base_dir / "tmp-clone"

    def _fake_prepare(*_: Any, **__: Any) -> tuple[Any, Path, dict[str, Any]]:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        repo = type("Repo", (), {"full_name": "demo/repo"})()
        return repo, tmp_dir, {}

    def _fake_stage(*_: Any, **kwargs: Any) -> bool:
        calls.append(("stage", kwargs.get("force_ack")))
        return True

    def _fake_push(*_: Any, **kwargs: Any) -> None:
        calls.append(("push", kwargs.get("default_branch")))

    def _fail_force(*_: Any, **__: Any) -> None:
        raise AssertionError("force push non previsto")

    class _PhaseSpy:
        def __init__(self, _logger: Any, *, stage: str, customer: Any = None) -> None:  # noqa: D401 - helper test
            stages.append(stage)
            self.stage = stage
            self.customer = customer

        def __enter__(self) -> "_PhaseSpy":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def set_artifacts(self, _: Any) -> None:
            return None

    monkeypatch.setattr(github_utils, "phase_scope", _PhaseSpy)
    monkeypatch.setattr(github_utils, "_prepare_repo", _fake_prepare)
    monkeypatch.setattr(github_utils, "_stage_changes", _fake_stage)
    monkeypatch.setattr(github_utils, "_push_with_retry", _fake_push)
    monkeypatch.setattr(github_utils, "_force_push_with_lease", _fail_force)

    github_utils.push_output_to_github(
        ctx,
        github_token="token456",  # noqa: S106 - token fittizio per test
    )

    assert ("stage", None) in calls
    assert any(call[0] == "push" for call in calls)
    assert stages == ["prepare_repo", "stage_changes", "push_with_retry"]
    assert not tmp_dir.exists()


def test_push_output_to_github_force_push_requires_ack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _make_context(tmp_path)

    tmp_dir = ctx.base_dir / "tmp-force"

    def _fake_prepare(*_: Any, **__: Any) -> tuple[Any, Path, dict[str, Any]]:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        repo = type("Repo", (), {"full_name": "demo/repo"})()
        return repo, tmp_dir, {}

    monkeypatch.setattr(github_utils, "_prepare_repo", _fake_prepare)
    monkeypatch.setattr(github_utils, "_stage_changes", lambda *a, **k: True)

    with pytest.raises(ForcePushError):
        github_utils.push_output_to_github(
            ctx,
            github_token="tok",  # noqa: S106 - token fittizio per test
            force_push=True,
        )

    assert tmp_dir.exists() is False


def test_stage_changes_commits_and_logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorded: list[str] = []

    class _Recorder:
        def info(self, msg: str, *, extra: dict[str, Any] | None = None) -> None:  # pragma: no cover - simple logger
            recorded.append(msg)

    called: dict[str, Any] = {}

    def _fake_stage_and_commit(*_: Any, **kwargs: Any) -> bool:
        called.update(kwargs)
        return False

    monkeypatch.setattr(github_utils, "_stage_and_commit", _fake_stage_and_commit)

    res = github_utils._stage_changes(tmp_path, {}, slug="demo", force_ack=None, logger=_Recorder())  # type: ignore[arg-type]

    assert res is False
    assert any("Nessuna modifica" in msg for msg in recorded)
    assert called["commit_msg"].startswith("Aggiornamento contenuto KB")


@pytest.mark.push
def test_should_push_respects_env_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _make_context(tmp_path)
    ctx.env["TIMMY_NO_GITHUB"] = "true"
    assert github_utils.should_push(ctx) is False

    ctx.env.clear()
    monkeypatch.setenv("SKIP_GITHUB_PUSH", "1")
    assert github_utils.should_push(ctx) is False

    monkeypatch.delenv("SKIP_GITHUB_PUSH", raising=False)
    assert github_utils.should_push(ctx) is True


@pytest.mark.push
def test_lease_lock_blocks_second_acquisition(tmp_path: Path) -> None:
    base_dir = tmp_path / "workspace"
    base_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tests.github.lock")

    lock_one = github_utils.LeaseLock(base_dir, slug="demo", logger=logger, timeout_s=0.3, poll_interval_s=0.05)
    lock_one.acquire()
    try:
        lock_two = github_utils.LeaseLock(base_dir, slug="demo", logger=logger, timeout_s=0.1, poll_interval_s=0.02)
        with pytest.raises(PushError):
            lock_two.acquire()
    finally:
        lock_one.release()

    lock_three = github_utils.LeaseLock(base_dir, slug="demo", logger=logger, timeout_s=0.1, poll_interval_s=0.02)
    lock_three.acquire()
    lock_three.release()


def test_push_with_retry_recovers_after_transient(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], str]] = []
    push_failures = {"count": 0}

    def _fake_run(cmd: list[str], *, cwd: Path, env: dict[str, Any] | None, op: str) -> None:
        calls.append((tuple(cmd), op))
        if cmd[:3] == ["git", "push", "origin"] and push_failures["count"] == 0:
            push_failures["count"] += 1
            raise github_utils.CmdError(
                "push failed",
                cmd=cmd,
                attempts=2,
                attempt=1,
                op=op,
                stdout="err",
                stderr="err",
            )

    monkeypatch.setattr(github_utils, "_run", _fake_run)

    logger = logging.getLogger("tests.github.retry")
    github_utils._push_with_retry(tmp_path, {}, "main", logger=logger, redact_logs=False)

    push_calls = [c for c in calls if c[0][:3] == ("git", "push", "origin")]
    pull_calls = [c for c in calls if c[0][:4] == ("git", "pull", "--rebase", "origin")]
    assert len(push_calls) == 2
    assert len(pull_calls) == 1


def test_push_with_retry_raises_after_double_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _always_fail(cmd: list[str], *, cwd: Path, env: dict[str, Any] | None, op: str) -> None:
        raise github_utils.CmdError("failure", cmd=cmd, attempts=1, attempt=1, op=op, stdout="err", stderr="err")

    monkeypatch.setattr(github_utils, "_run", _always_fail)

    with pytest.raises(PushError):
        github_utils._push_with_retry(
            tmp_path, {}, "main", logger=logging.getLogger("tests.github.retry"), redact_logs=False
        )


def test_force_push_with_lease_uses_remote_sha(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], str]] = []

    def _fake_run(cmd: list[str], *, cwd: Path, env: dict[str, Any] | None, op: str) -> None:
        calls.append((tuple(cmd), op))

    def _fake_git_rev_parse(ref: str, *, cwd: Path, env: dict[str, Any] | None) -> str:
        if ref.startswith("origin/"):
            return "remote-sha"
        return "local-sha"

    monkeypatch.setattr(github_utils, "_run", _fake_run)
    monkeypatch.setattr(github_utils, "_git_rev_parse", _fake_git_rev_parse)

    logger = logging.getLogger("tests.github.force")
    github_utils._force_push_with_lease(
        tmp_dir=tmp_path,
        env={},
        default_branch="main",
        force_ack="ack-token",
        logger=logger,
        redact_logs=False,
    )

    assert calls[0][0] == ("git", "fetch", "origin", "main")
    push_cmd = calls[-1][0]
    assert push_cmd[0:3] == ("git", "push", "--force-with-lease=refs/heads/main:remote-sha")
