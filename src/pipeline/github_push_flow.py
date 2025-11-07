# SPDX-License-Identifier: GPL-3.0-or-later
"""Funzioni operative per il workflow di push su GitHub."""

from __future__ import annotations

import base64
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from github import Github
from github.GithubException import GithubException

from pipeline.exceptions import PipelineError, PushError
from pipeline.logging_utils import get_structured_logger, redact_secrets
from pipeline.path_utils import ensure_within
from pipeline.proc_utils import CmdError, run_cmd

from .github_types import SupportsContext

__all__ = [
    "_prepare_tmp_dir",
    "_ensure_or_create_repo",
    "_sanitize_env",
    "_run",
    "_git_status_porcelain",
    "_git_rev_parse",
    "_copy_md_tree",
    "_mask_ack",
    "_stage_and_commit",
    "_stage_changes",
    "_push_with_retry",
    "_force_push_with_lease",
    "_prepare_repo",
]

logger = get_structured_logger("pipeline.github_push_flow")


def _prepare_tmp_dir(base_dir: Path) -> Path:
    parent = Path(tempfile.mkdtemp(prefix=".push_", dir=str(base_dir)))
    ensure_within(base_dir, parent)
    return parent / "repo"


def _ensure_or_create_repo(gh: Github, user: Any, repo_name: str, *, logger: logging.Logger, redact_logs: bool) -> Any:
    try:
        return user.get_repo(repo_name)
    except GithubException as exc:
        if getattr(exc, "status", None) != 404:
            raw = f"Errore accesso repository: {exc}"
            safe = redact_secrets(raw) if redact_logs else raw
            raise PipelineError(safe)
    try:
        return user.create_repo(repo_name, private=True, auto_init=False)
    except GithubException as exc:
        raw = f"Impossibile creare il repository: {exc}"
        safe = redact_secrets(raw) if redact_logs else raw
        raise PipelineError(safe)


def _sanitize_env(*envs: Mapping[str, Any], allow: Optional[Iterable[str]] = None) -> dict[str, str]:
    out: dict[str, str] = dict(os.environ)
    allow_set = set(allow or [])
    for env in envs:
        if not env:
            continue
        for key, value in env.items():
            if value is None:
                continue
            sk = str(key)
            if allow and sk not in allow_set:
                continue
            out[sk] = str(value)
    return out


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, Any] | None = None, op: str = "git") -> None:
    run_cmd(cmd, cwd=str(cwd) if cwd else None, env=env, capture=True, logger=logger, op=op)


def _git_status_porcelain(cwd: Path, env: dict[str, Any] | None = None) -> str:
    cp = run_cmd(
        ["git", "status", "--porcelain"],
        cwd=str(cwd),
        env=env,
        capture=True,
        logger=logger,
        op="git status",
    )
    return cp.stdout or ""


def _git_rev_parse(ref: str, cwd: Path, env: dict[str, Any] | None = None) -> str:
    cp = run_cmd(
        ["git", "rev-parse", ref],
        cwd=str(cwd),
        env=env,
        capture=True,
        logger=logger,
        op="git rev-parse",
    )
    return (cp.stdout or "").strip()


def _copy_md_tree(md_files: Sequence[Path], book_dir: Path, dst_root: Path) -> None:
    for src in md_files:
        dst = dst_root / src.relative_to(book_dir)
        ensure_within(dst_root, dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _mask_ack(tag: str) -> str:
    if not tag:
        return ""
    if len(tag) <= 4:
        return "***"
    return f"{tag[:2]}***{tag[-2:]}"


def _stage_and_commit(tmp_dir: Path, env: dict[str, Any] | None, *, commit_msg: str) -> bool:
    _run(["git", "add", "-A"], cwd=tmp_dir, env=env, op="git add")
    status = _git_status_porcelain(tmp_dir, env)
    if not status.strip():
        return False
    run_cmd(
        [
            "git",
            "-c",
            "user.name=Timmy KB",
            "-c",
            "user.email=kb+noreply@local",
            "commit",
            "-m",
            commit_msg,
        ],
        cwd=str(tmp_dir),
        env=env,
        capture=True,
        logger=logger,
        op="git commit",
    )
    return True


def _stage_changes(
    tmp_dir: Path,
    env: dict[str, Any] | None,
    *,
    slug: str,
    force_ack: str | None,
    logger: logging.Logger,
    stage_and_commit_fn: Any = None,
) -> bool:
    commit_msg = f"Aggiornamento contenuto KB per cliente {slug}"
    if force_ack:
        commit_msg = f"{commit_msg}\n\nForce-Ack: {force_ack}"
    if stage_and_commit_fn is None:
        stage_and_commit_fn = _stage_and_commit
    committed = stage_and_commit_fn(tmp_dir, env, commit_msg=commit_msg)
    if not committed:
        logger.info("Nessuna modifica da pubblicare (working dir identica)", extra={"slug": slug})
        return False
    return True


def _push_with_retry(
    tmp_dir: Path,
    env: dict[str, Any] | None,
    default_branch: str,
    *,
    logger: logging.Logger,
    redact_logs: bool,
    run_func: Any = None,
) -> None:
    if run_func is None:
        run_func = _run

    def _attempt_push() -> None:
        run_func(["git", "push", "origin", default_branch], cwd=tmp_dir, env=env, op="git push")

    try:
        logger.info("Push su origin/%s", default_branch)
        _attempt_push()
    except CmdError:
        logger.warning("Push rifiutato. Tentativo di sincronizzazione (pull --rebase) e nuovo push...")
        try:
            run_func(
                ["git", "pull", "--rebase", "origin", default_branch],
                cwd=tmp_dir,
                env=env,
                op="git pull --rebase",
            )
            _attempt_push()
        except CmdError as exc:
            raw = (
                "Push fallito dopo retry con rebase. "
                "Possibili conflitti tra contenuto locale e remoto. "
                "Suggerimenti: usare un branch dedicato (GIT_DEFAULT_BRANCH) e aprire una PR, "
                "oppure abilitare il force push nell'orchestratore."
            )
            safe = redact_secrets(raw) if redact_logs else raw
            raise PushError(safe) from exc


def _force_push_with_lease(
    tmp_dir: Path,
    env: dict[str, Any] | None,
    default_branch: str,
    force_ack: str,
    *,
    logger: logging.Logger,
    redact_logs: bool,
    run_func: Any | None = None,
    git_rev_parse_fn: Any | None = None,
) -> None:
    if run_func is None:
        run_func = _run
    if git_rev_parse_fn is None:
        git_rev_parse_fn = _git_rev_parse

    run_func(["git", "fetch", "origin", default_branch], cwd=tmp_dir, env=env, op="git fetch")
    remote_sha = git_rev_parse_fn(f"origin/{default_branch}", cwd=tmp_dir, env=env)
    local_sha = git_rev_parse_fn("HEAD", cwd=tmp_dir, env=env)
    logger.info(
        "Force push governato (with-lease)",
        extra={
            "branch": default_branch,
            "local_sha": local_sha,
            "remote_sha": remote_sha,
            "force_ack": _mask_ack(force_ack),
        },
    )
    run_func(
        [
            "git",
            "push",
            f"--force-with-lease=refs/heads/{default_branch}:{remote_sha}",
            "origin",
            default_branch,
        ],
        cwd=tmp_dir,
        env=env,
        op="git push --force-with-lease",
    )


def _prepare_repo(
    context: SupportsContext,
    *,
    github_token: str,
    md_files: Sequence[Path],
    default_branch: str,
    base_dir: Path,
    book_dir: Path,
    redact_logs: bool,
    logger: logging.Logger,
) -> tuple[Any, Path, dict[str, Any]]:
    gh = Github(github_token)
    try:
        user = gh.get_user()
    except GithubException as exc:
        raw = f"Errore autenticazione GitHub: {exc}"
        safe = redact_secrets(raw) if redact_logs else raw
        raise PipelineError(safe, slug=getattr(context, "slug", None))

    repo_name = f"timmy-kb-{context.slug}"
    repo = _ensure_or_create_repo(gh, user, repo_name, logger=logger, redact_logs=redact_logs)
    remote_url = repo.clone_url

    tmp_dir = _prepare_tmp_dir(base_dir)
    header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
    extra_env = {"GIT_HTTP_EXTRAHEADER": f"Authorization: Basic {header}"}
    allow = {"GIT_HTTP_EXTRAHEADER", "GIT_SSH_COMMAND"}
    env = _sanitize_env(getattr(context, "env", {}) or {}, extra_env, allow=allow)

    logger.info(
        "Clonazione repo remoto in working dir temporanea",
        extra={"slug": context.slug, "file_path": str(tmp_dir)},
    )

    def _to_bool(value: object) -> bool:
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "on"}

    shallow_env = (getattr(context, "env", {}) or {}).get("USE_SHALLOW_CLONE")
    use_shallow = True if shallow_env is None else _to_bool(shallow_env)
    env_override = os.environ.get("USE_SHALLOW_CLONE")
    if shallow_env is None and env_override is not None:
        use_shallow = _to_bool(env_override)

    if use_shallow:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        _run(["git", "init"], cwd=tmp_dir, env=env, op="git init")
        _run(["git", "remote", "add", "origin", remote_url], cwd=tmp_dir, env=env, op="git remote add")
        try:
            _run(["git", "fetch", "origin", default_branch, "--depth=1"], cwd=tmp_dir, env=env, op="git fetch")
        except CmdError:
            pass
    else:
        _run(["git", "clone", remote_url, str(tmp_dir)], env=env, op="git clone")

    exists_remote_branch = True
    try:
        run_cmd(
            ["git", "rev-parse", f"origin/{default_branch}"],
            cwd=str(tmp_dir),
            env=env,
            capture=True,
            logger=logger,
            op="git rev-parse",
        )
    except CmdError:
        exists_remote_branch = False

    if exists_remote_branch:
        _run(
            ["git", "checkout", "-B", default_branch, f"origin/{default_branch}"],
            cwd=tmp_dir,
            env=env,
            op="git checkout",
        )
        logger.info(
            "Pull --rebase per sincronizzazione iniziale",
            extra={"slug": context.slug, "branch": default_branch},
        )
        _run(
            ["git", "pull", "--rebase", "origin", default_branch],
            cwd=tmp_dir,
            env=env,
            op="git pull --rebase",
        )
    else:
        _run(["git", "checkout", "-B", default_branch], cwd=tmp_dir, env=env, op="git checkout")

    logger.info(
        "Preparazione contenuti da book/",
        extra={"slug": context.slug, "file_path": str(book_dir)},
    )
    _copy_md_tree(md_files, book_dir, tmp_dir)

    return repo, tmp_dir, env
