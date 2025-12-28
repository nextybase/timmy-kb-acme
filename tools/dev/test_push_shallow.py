#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_TOOLS_DIR = next(p for p in Path(__file__).resolve().parents if p.name == "tools")
_REPO_ROOT = _TOOLS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools._bootstrap import bootstrap_repo_src

# ENTRYPOINT BOOTSTRAP - consentito: abilita import pipeline.* per test push.
REPO_ROOT = bootstrap_repo_src()


@dataclass
class _Ctx:
    slug: str
    md_dir: Path
    base_dir: Path
    env: dict[str, Any]


def _run(cmd: list[str], cwd: Optional[Path] = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def main() -> int:
    # Stub PyGithub to avoid external dependency in this integration
    import sys as _sys
    import types

    github_mod = types.ModuleType("github")

    class _Github:
        def __init__(self, *a, **k):
            pass

        def get_user(self):
            class _U:  # pragma: no cover - not used directly
                pass

            return _U()

    github_mod.Github = _Github
    github_exc_mod = types.ModuleType("github.GithubException")

    class _GithubException(Exception):
        pass

    github_exc_mod.GithubException = _GithubException
    _sys.modules["github"] = github_mod
    _sys.modules["github.GithubException"] = github_exc_mod

    # Patch pipeline.env_utils to add missing helpers expected by github_utils
    import importlib

    real_env = importlib.import_module("pipeline.env_utils")
    if not hasattr(real_env, "get_force_allowed_branches"):

        def _get_force_allowed_branches(context: Any) -> list[str]:
            return []

        setattr(real_env, "get_force_allowed_branches", _get_force_allowed_branches)
    if not hasattr(real_env, "is_branch_allowed_for_force"):

        def _is_branch_allowed_for_force(branch: str, context: Any, allow_if_unset: bool = True) -> bool:
            return True

        setattr(real_env, "is_branch_allowed_for_force", _is_branch_allowed_for_force)

    import pipeline.github_utils as gu

    # Arrange temp workspace
    tmp_root = Path(tempfile.mkdtemp(prefix="push-shallow-"))
    base_dir = tmp_root / "workspace"
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "README.md").write_text("# Dummy KB\n\nHello shallow clone!\n", encoding="utf-8")

    # Create local bare remote
    bare = tmp_root / "remote.git"
    _run(["git", "init", "--bare", str(bare)])

    # Monkeypatch ensure/create repo to return a dummy with clone_url to local bare
    class _Repo:
        def __init__(self, url: str) -> None:
            self.clone_url = url
            self.full_name = url

    def _fake_ensure_repo(gh: Any, user: Any, repo_name: str, *, logger: Any, redact_logs: bool) -> Any:
        return _Repo(str(bare))

    old_fn = gu._ensure_or_create_repo
    gu._ensure_or_create_repo = _fake_ensure_repo  # type: ignore[assignment]

    # Context and env
    os.environ["USE_SHALLOW_CLONE"] = "1"
    ctx = _Ctx(slug="shallow-smoke", md_dir=book_dir, base_dir=base_dir, env={})

    try:
        # Act
        gu.push_output_to_github(ctx, github_token="dummy", do_push=True, force_push=False, redact_logs=False)
        # Assert: check that remote has the branch with at least one commit
        # Clone remote shallow to verify HEAD exists
        verify = tmp_root / "verify"
        _run(["git", "clone", str(bare), str(verify)])
        # Ensure we have the pushed branch
        try:
            _run(["git", "checkout", "-B", "main", "origin/main"], cwd=verify)
        except Exception:
            _run(["git", "fetch", "origin"], cwd=verify)
            _run(["git", "checkout", "-B", "main", "origin/main"], cwd=verify)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(verify), text=True).strip()
        print(f"OK shallow push test, HEAD={head}")
        return 0
    finally:
        # Restore monkeypatch
        gu._ensure_or_create_repo = old_fn  # type: ignore[assignment]
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
