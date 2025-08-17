# tests/test_github_utils.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List
import logging
import pytest

from pipeline.github_utils import push_output_to_github
from pipeline.exceptions import PipelineError

# --- Mini contesto compatibile con github_utils (duck typing) ---
@dataclass
class _Ctx:
    slug: str
    md_dir: Path
    env: dict  # usato per risolvere il branch di default, se supportato dal modulo


def _enable_propagation(logger_name: str, monkeypatch) -> logging.Logger:
    """Abilita temporaneamente la propagazione per consentire a caplog di catturare i record."""
    lg = logging.getLogger(logger_name)
    monkeypatch.setattr(lg, "propagate", True, raising=False)
    return lg


# ------------
# push_output_to_github
# ------------
def test_push_raises_if_token_missing(tmp_path: Path):
    md = tmp_path / "book"
    md.mkdir()
    (md / "a.md").write_text("# A\n", encoding="utf-8")
    ctx = _Ctx(slug="dummy", md_dir=md, env={})
    with pytest.raises(PipelineError):
        push_output_to_github(ctx, github_token="", confirm_push=True)


def test_push_returns_if_no_md_files(monkeypatch, tmp_path: Path, caplog):
    md = tmp_path / "book"
    md.mkdir()
    # solo file non-md
    (md / "a.txt").write_text("x", encoding="utf-8")
    ctx = _Ctx(slug="dummy", md_dir=md, env={})

    # se provasse a usare PyGithub o git falliremmo: confermiamo che esce prima
    called: dict[str, Any] = {"github": False, "git": False}

    class _DummyGH:
        def __init__(self, *_a, **_k):
            called["github"] = True

    monkeypatch.setattr("pipeline.github_utils.Github", _DummyGH, raising=True)

    def _fake_run(*_a, **_k):
        called["git"] = True
        return None

    monkeypatch.setattr("pipeline.github_utils.subprocess.run", _fake_run, raising=True)

    _enable_propagation("pipeline.github_utils", monkeypatch)
    with caplog.at_level("WARNING", logger="pipeline.github_utils"):
        push_output_to_github(ctx, github_token="x", confirm_push=True)
        assert any(
            r.name == "pipeline.github_utils" and r.levelname == "WARNING" for r in caplog.records
        ), f"Log WARNING atteso non presente. Records: {[ (r.name, r.levelname, r.getMessage()) for r in caplog.records ]}"
    assert called["github"] is False and called["git"] is False


def test_push_short_circuits_on_confirm_push_false(monkeypatch, tmp_path: Path, caplog):
    md = tmp_path / "book"
    md.mkdir()
    (md / "a.md").write_text("# A\n", encoding="utf-8")
    (md / "b.md.bak").write_text("# backup\n", encoding="utf-8")
    ctx = _Ctx(slug="dummy", md_dir=md, env={})

    called = {"github": False, "git": False}

    class _RaiseIfCalled:
        def __init__(self, *_a, **_k):
            called["github"] = True
            raise AssertionError("Github() non dovrebbe essere chiamato con confirm_push=False")

    monkeypatch.setattr("pipeline.github_utils.Github", _RaiseIfCalled, raising=True)

    def _raise_run(*_a, **_k):
        called["git"] = True
        raise AssertionError("subprocess.run non dovrebbe essere chiamato con confirm_push=False")

    monkeypatch.setattr("pipeline.github_utils.subprocess.run", _raise_run, raising=True)

    _enable_propagation("pipeline.github_utils", monkeypatch)
    with caplog.at_level("INFO", logger="pipeline.github_utils"):
        push_output_to_github(ctx, github_token="token", confirm_push=False)
        assert any(
            r.name == "pipeline.github_utils" and r.levelname == "INFO" for r in caplog.records
        ), f"Log INFO atteso non presente. Records: {[ (r.name, r.levelname, r.getMessage()) for r in caplog.records ]}"
    assert called["github"] is False and called["git"] is False


def test_push_copies_only_md_excluding_bak_and_uses_selected_branch(monkeypatch, tmp_path: Path):
    """
    Eseguiamo il flusso "happy path" senza rete:
    - mock di PyGithub e di git (subprocess.run)
    - TemporaryDirectory -> cartella controllata per ispezionare i file copiati
    - verifichiamo che ci siano solo .md (no .bak, no .txt) e che il checkout usi il branch risolto
    """
    md = tmp_path / "book"
    (md / "nested").mkdir(parents=True)
    (md / "a.md").write_text("# A\n", encoding="utf-8")
    (md / "nested" / "b.md").write_text("# B\n", encoding="utf-8")
    (md / "c.md.bak").write_text("# backup\n", encoding="utf-8")
    (md / "d.txt").write_text("nope\n", encoding="utf-8")

    ctx = _Ctx(slug="dummy", md_dir=md, env={"GIT_DEFAULT_BRANCH": "dev"})

    # Stub PyGithub (user + repo minimal)
    class _Repo:
        full_name = "user/timmy-kb-dummy"

        @property
        def clone_url(self):
            return "https://github.com/user/timmy-kb-dummy.git"

    class _User:
        def get_repo(self, name: str):
            return _Repo()

        def create_repo(self, name: str, private: bool = True):
            return _Repo()

    class _GH:
        def __init__(self, token: str):
            assert token == "gh_token"

        def get_user(self):
            return _User()

    monkeypatch.setattr("pipeline.github_utils.Github", _GH, raising=True)

    # intercettiamo tutte le chiamate git
    git_calls: List[List[str]] = []

    def _fake_run(args, cwd=None, check=None):
        git_calls.append(list(args))

        class _P:
            ...

        return _P()

    monkeypatch.setattr("pipeline.github_utils.subprocess.run", _fake_run, raising=True)

    # Forziamo TemporaryDirectory su una cartella controllata per ispezione
    work = tmp_path / "tmprepo"
    work.mkdir()

    class _TD:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return str(work)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("pipeline.github_utils.tempfile.TemporaryDirectory", _TD, raising=True)

    push_output_to_github(ctx, github_token="gh_token", confirm_push=True)

    # Verifica: solo .md copiati, preservando struttura
    copied = sorted(str(p.relative_to(work)).replace("\\", "/") for p in work.rglob("*") if p.is_file())
    assert copied == ["a.md", "nested/b.md"]

    # Verifica: è stato usato il branch 'dev' (se il modulo esegue checkout -b)
    assert any(call[:3] == ["git", "checkout", "-b"] and call[3] == "dev" for call in git_calls) or \
           any(call[:2] == ["git", "checkout"] and call[2] == "dev" for call in git_calls)
