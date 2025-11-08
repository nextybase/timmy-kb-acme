# SPDX-License-Identifier: GPL-3.0-only
"""Test per la pipeline GitHub refactorata (push orchestrator)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pytest

from pipeline import github_push_flow as github_flow
from pipeline import github_utils
from pipeline.exceptions import ForcePushError, PushError
from pipeline.github_env_flags import should_push
from pipeline.github_lease import LeaseLock

GIT_BIN = shutil.which("git") or "git"


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
    book_dir = ctx.md_dir
    md_files = list(book_dir.glob("*.md"))

    def _fake_prepare(*_: Any, **__: Any) -> tuple[Any, Path, dict[str, Any]]:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        repo = type("Repo", (), {"full_name": "demo/repo"})()
        github_flow._copy_md_tree(md_files, book_dir, tmp_dir)
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
    monkeypatch.setattr(github_utils, "_stage_changes_flow", _fake_stage)
    monkeypatch.setattr(github_utils, "_push_with_retry_flow", _fake_push)
    monkeypatch.setattr(github_utils, "_force_push_with_lease_flow", _fail_force)

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
    monkeypatch.setattr(github_utils, "_stage_changes_flow", lambda *a, **k: True)

    with pytest.raises(ForcePushError):
        github_utils.push_output_to_github(
            ctx,
            github_token="tok",  # noqa: S106 - token fittizio per test
            force_push=True,
        )

    assert tmp_dir.exists() is False


def test_push_output_to_github_force_push_rejects_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _make_context(tmp_path)
    ctx.env["GIT_DEFAULT_BRANCH"] = "feature/docs"
    ctx.env["GIT_FORCE_ALLOWED_BRANCHES"] = "release/*"

    tmp_dir = ctx.base_dir / "tmp-force-branch"

    def _fake_prepare(*_: Any, **__: Any) -> tuple[Any, Path, dict[str, Any]]:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        repo = type("Repo", (), {"full_name": "demo/repo"})()
        return repo, tmp_dir, {}

    monkeypatch.setattr(github_utils, "_prepare_repo", _fake_prepare)
    monkeypatch.setattr(github_utils, "_stage_changes_flow", lambda *a, **k: True)

    with pytest.raises(ForcePushError) as excinfo:
        github_utils.push_output_to_github(
            ctx,
            github_token="tok",  # noqa: S106 - token fittizio per test
            force_push=True,
            force_ack="ticket-123",
        )

    assert "Force push NON consentito" in str(excinfo.value)
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

    monkeypatch.setattr(github_flow, "_stage_and_commit", _fake_stage_and_commit)

    res = github_flow._stage_changes(tmp_path, {}, slug="demo", force_ack=None, logger=_Recorder())  # type: ignore[arg-type]

    assert res is False
    assert any("Nessuna modifica" in msg for msg in recorded)
    assert called["commit_msg"].startswith("Aggiornamento contenuto KB")


@pytest.mark.push
def test_should_push_respects_env_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _make_context(tmp_path)
    ctx.env["TIMMY_NO_GITHUB"] = "true"
    assert should_push(ctx) is False

    ctx.env.clear()
    monkeypatch.setenv("SKIP_GITHUB_PUSH", "1")
    assert should_push(ctx) is False

    monkeypatch.delenv("SKIP_GITHUB_PUSH", raising=False)
    assert should_push(ctx) is True


@pytest.mark.push
def test_lease_lock_blocks_second_acquisition(tmp_path: Path) -> None:
    base_dir = tmp_path / "workspace"
    base_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tests.github.lock")

    lock_one = LeaseLock(base_dir, slug="demo", logger=logger, timeout_s=0.3, poll_interval_s=0.05)
    lock_one.acquire()
    try:
        lock_two = LeaseLock(base_dir, slug="demo", logger=logger, timeout_s=0.1, poll_interval_s=0.02)
        with pytest.raises(PushError):
            lock_two.acquire()
    finally:
        lock_one.release()

    lock_three = LeaseLock(base_dir, slug="demo", logger=logger, timeout_s=0.1, poll_interval_s=0.02)
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

    monkeypatch.setattr(github_flow, "_run", _fake_run)

    logger = logging.getLogger("tests.github.retry")
    github_flow._push_with_retry(tmp_path, {}, "main", logger=logger, redact_logs=False)

    push_calls = [c for c in calls if c[0][:3] == ("git", "push", "origin")]
    pull_calls = [c for c in calls if c[0][:4] == ("git", "pull", "--rebase", "origin")]
    assert len(push_calls) == 2
    assert len(pull_calls) == 1


def test_push_with_retry_raises_after_double_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _always_fail(cmd: list[str], *, cwd: Path, env: dict[str, Any] | None, op: str) -> None:
        raise github_utils.CmdError("failure", cmd=cmd, attempts=1, attempt=1, op=op, stdout="err", stderr="err")

    monkeypatch.setattr(github_flow, "_run", _always_fail)

    with pytest.raises(PushError):
        github_flow._push_with_retry(
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

    monkeypatch.setattr(github_flow, "_run", _fake_run)
    monkeypatch.setattr(github_flow, "_git_rev_parse", _fake_git_rev_parse)

    logger = logging.getLogger("tests.github.force")
    github_flow._force_push_with_lease(
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


def _run_git(args: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run([GIT_BIN, *args], cwd=cwd, check=True)


def _seed_remote_repo(tmp_path: Path, *, branch: str = "main") -> Path:
    """Crea un repo bare con un branch iniziale popolato."""
    safe_branch = branch.replace("/", "-")
    remote_repo = tmp_path / f"remote-{safe_branch}.git"
    _run_git(["init", "--bare", remote_repo.as_posix()])

    seed_dir = tmp_path / f"seed-{safe_branch}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    _run_git(["init"], cwd=seed_dir)
    _run_git(["config", "user.name", "Smoke Tester"], cwd=seed_dir)
    _run_git(["config", "user.email", "smoke@example.com"], cwd=seed_dir)
    (seed_dir / "README.md").write_text("seed", encoding="utf-8")
    _run_git(["add", "README.md"], cwd=seed_dir)
    _run_git(["commit", "-m", "seed"], cwd=seed_dir)
    _run_git(["branch", "-M", branch], cwd=seed_dir)
    _run_git(["remote", "add", "origin", remote_repo.as_posix()], cwd=seed_dir)
    _run_git(["push", "-u", "origin", branch], cwd=seed_dir)
    subprocess.run(
        [GIT_BIN, "--git-dir", str(remote_repo), "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
        check=True,
    )
    return remote_repo


def test_push_output_to_github_end_to_end_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    remote_repo = _seed_remote_repo(tmp_path, branch="main")

    ctx = _make_context(tmp_path)
    ctx.env["GIT_DEFAULT_BRANCH"] = "main"

    captured_plan: dict[str, Any] = {}
    original_build_plan = github_utils._build_push_plan

    def _build_push_plan_with_trace(*args: Any, **kwargs: Any) -> Any:
        plan = original_build_plan(*args, **kwargs)
        captured_plan["plan"] = plan
        return plan

    monkeypatch.setattr(github_utils, "_build_push_plan", _build_push_plan_with_trace)

    copies: list[tuple[list[Path], Path, Path]] = []
    original_copy_tree = github_flow._copy_md_tree
    stub_called = {"value": False}

    def _copy_md_tree_with_trace(md_files: Sequence[Path], book_dir: Path, dst_root: Path) -> None:
        copies.append((list(md_files), book_dir, dst_root))
        original_copy_tree(md_files, book_dir, dst_root)

    monkeypatch.setattr(github_flow, "_copy_md_tree", _copy_md_tree_with_trace)

    status_snapshot: dict[str, str] = {}
    original_stage_and_commit = github_flow._stage_and_commit

    def _stage_and_commit_with_trace(
        tmp_dir: Path,
        env: dict[str, Any] | None,
        *,
        commit_msg: str,
    ) -> bool:
        status_snapshot["files_before"] = sorted(p.name for p in tmp_dir.glob("*") if p.is_file())
        status_snapshot["tree_before"] = sorted(str(p.relative_to(tmp_dir)) for p in tmp_dir.rglob("*.md"))
        before = subprocess.run(
            [GIT_BIN, "status", "--short"],
            cwd=tmp_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        status_snapshot["before"] = before.stdout
        result = original_stage_and_commit(tmp_dir, env, commit_msg=commit_msg)
        after = subprocess.run(
            [GIT_BIN, "status", "--short"],
            cwd=tmp_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        status_snapshot["after"] = after.stdout
        status_snapshot["files_after"] = sorted(p.name for p in tmp_dir.glob("*") if p.is_file())
        status_snapshot["tree_after"] = sorted(str(p.relative_to(tmp_dir)) for p in tmp_dir.rglob("*.md"))
        return result

    monkeypatch.setattr(github_flow, "_stage_and_commit", _stage_and_commit_with_trace)
    monkeypatch.setattr(github_utils, "_stage_and_commit", _stage_and_commit_with_trace)

    def _prepare_repo(
        context: Any,
        *,
        github_token: str,
        md_files: list[Path],
        default_branch: str,
        base_dir: Path,
        book_dir: Path,
        redact_logs: bool,
        logger: logging.Logger,
    ) -> tuple[Any, Path, dict[str, Any]]:
        stub_called["value"] = True
        tmp_dir = github_flow._prepare_tmp_dir(base_dir)
        _run_git(["clone", remote_repo.as_posix(), str(tmp_dir)])
        _run_git(["checkout", "-B", default_branch], cwd=tmp_dir)
        github_flow._copy_md_tree(md_files, book_dir, tmp_dir)
        repo = type("Repo", (), {"full_name": "smoke/repo"})()
        return repo, tmp_dir, {}

    monkeypatch.setattr(github_utils, "_prepare_repo", _prepare_repo)

    github_utils.push_output_to_github(
        ctx,
        github_token="smoketoken",  # noqa: S106 - token fittizio
        do_push=True,
    )

    plan = captured_plan.get("plan")
    assert plan is not None, "push plan not built"
    assert len(plan.md_files) > 0, "nessun markdown nel push plan"
    status_snapshot["plan_md_files"] = [str(p) for p in plan.md_files]
    status_snapshot["book_dir"] = str(plan.book_dir)
    status_snapshot["book_contents"] = sorted(p.name for p in plan.book_dir.glob("*.md"))
    status_snapshot["copies"] = [([str(p) for p in bundle[0]], str(bundle[1]), str(bundle[2])) for bundle in copies]
    status_snapshot["prepare_called"] = stub_called["value"]

    assert status_snapshot.get("before", "").strip(), f"git status before commit empty: {status_snapshot}"
    assert status_snapshot.get("after", "").strip() == "", f"git status after commit not clean: {status_snapshot}"

    show = subprocess.run(
        [GIT_BIN, "--git-dir", str(remote_repo), "show", "main:foo.md"],
        capture_output=True,
        text=True,
    )
    assert show.returncode == 0, f"git show failed with code {show.returncode}: {show.stderr}\nstatus={status_snapshot}"
    assert "# demo" in show.stdout


def test_push_output_to_github_force_push_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    remote_repo = _seed_remote_repo(tmp_path, branch="feature/docs")

    ctx = _make_context(tmp_path)
    ctx.env["GIT_DEFAULT_BRANCH"] = "feature/docs"
    ctx.env["GIT_FORCE_ALLOWED_BRANCHES"] = "feature/*"

    captured_plan: dict[str, Any] = {}
    original_build_plan = github_utils._build_push_plan

    def _build_push_plan_with_trace(*args: Any, **kwargs: Any) -> Any:
        plan = original_build_plan(*args, **kwargs)
        captured_plan["plan"] = plan
        return plan

    monkeypatch.setattr(github_utils, "_build_push_plan", _build_push_plan_with_trace)

    force_calls: list[tuple[str, str | None]] = []

    def _force_push_with_trace(
        tmp_dir: Path,
        env: dict[str, Any] | None,
        default_branch: str,
        force_ack: str,
        *,
        logger: logging.Logger,
        redact_logs: bool,
    ) -> None:
        force_calls.append((default_branch, force_ack))
        github_flow._force_push_with_lease(
            tmp_dir,
            env,
            default_branch,
            force_ack,
            logger=logger,
            redact_logs=redact_logs,
        )

    monkeypatch.setattr(github_utils, "_force_push_with_lease_flow", _force_push_with_trace)
    monkeypatch.setattr(
        github_utils,
        "_push_with_retry_flow",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("push_with_retry non atteso")),
    )

    copies: list[tuple[list[Path], Path, Path]] = []
    original_copy_tree = github_flow._copy_md_tree

    def _copy_md_tree_with_trace(md_files: Sequence[Path], book_dir: Path, dst_root: Path) -> None:
        copies.append((list(md_files), book_dir, dst_root))
        original_copy_tree(md_files, book_dir, dst_root)

    monkeypatch.setattr(github_flow, "_copy_md_tree", _copy_md_tree_with_trace)

    def _prepare_repo(
        context: Any,
        *,
        github_token: str,
        md_files: list[Path],
        default_branch: str,
        base_dir: Path,
        book_dir: Path,
        redact_logs: bool,
        logger: logging.Logger,
    ) -> tuple[Any, Path, dict[str, Any]]:
        tmp_dir = github_flow._prepare_tmp_dir(base_dir)
        _run_git(["clone", remote_repo.as_posix(), str(tmp_dir)])
        _run_git(["checkout", "-B", default_branch], cwd=tmp_dir)
        github_flow._copy_md_tree(md_files, book_dir, tmp_dir)
        repo = type("Repo", (), {"full_name": "smoke/repo"})()
        return repo, tmp_dir, {}

    monkeypatch.setattr(github_utils, "_prepare_repo", _prepare_repo)

    github_utils.push_output_to_github(
        ctx,
        github_token="force-token",  # noqa: S106 - token fittizio
        do_push=True,
        force_push=True,
        force_ack="ticket-123",
    )

    plan = captured_plan.get("plan")
    assert plan is not None
    assert plan.default_branch == "feature/docs"
    assert force_calls == [("feature/docs", "ticket-123")]
    assert copies, "nessuna copia di markdown eseguita"

    show = subprocess.run(
        [GIT_BIN, "--git-dir", str(remote_repo), "show", "feature/docs:foo.md"],
        capture_output=True,
        text=True,
    )
    assert show.returncode == 0, show.stderr
    assert "# demo" in show.stdout
