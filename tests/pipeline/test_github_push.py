"""Test per la pipeline GitHub refactorata (push orchestrator)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from pipeline import github_utils
from pipeline.exceptions import ForcePushError


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
