# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/github_utils.py
"""Utility GitHub per la pipeline Timmy-KB.

Cosa fa
-------
- **Rileva o crea** il repository remoto del cliente (`timmy-kb-<slug>`).
- **Pubblica** i soli file Markdown presenti in `book/` (escludendo `.bak`), preservando lâ€™albero.
- **Gestisce branch di default** con SSoT di chiavi dâ€™ambiente (`DEFAULT_GIT_BRANCH_ENV_KEYS`).
- **Esegue push incrementale** con retry (pull --rebase â†’ nuovo push) oppure
  **force push governato** (`--force-with-lease`) con allow-list di branch e `force_ack`.
- **Sicurezza path**: STRONG guard con `ensure_within` per tutte le scritture/cancellezioni.
- **Credenziali via env**: header HTTP Basic in `GIT_HTTP_EXTRAHEADER` (il token non compare).
- **Working dir temporanea sicura** sotto la base cliente:
  il clone avviene in una sottocartella **non esistente** (no `git clone` in dir giÃ  presente).

API principale (stabile)
------------------------
push_output_to_github(
    context,
    *,
    github_token: str,
    do_push: bool = True,
    force_push: bool = False,
    force_ack: str | None = None,
    redact_logs: bool = False,
) -> None

Dove `context` espone almeno:
  - `slug: str`
  - `md_dir: Path`
  - `env: dict` (opzionale)
  - `base_dir: Path`
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import tempfile
import time
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence, runtime_checkable

from github import Github
from github.GithubException import GithubException

from pipeline.constants import DEFAULT_GIT_BRANCH_ENV_KEYS
from pipeline.env_utils import get_env_var  # ðŸ” env resolver (no masking qui)

try:
    from pipeline.env_utils import get_force_allowed_branches  # per log/errore esplicativo
except ImportError:  # pragma: no cover

    def get_force_allowed_branches(context: Any) -> list[str]:
        env_map = getattr(context, "env", {}) or {}
        raw = env_map.get("GIT_FORCE_ALLOWED_BRANCHES")
        if raw is None:
            raw = os.environ.get("GIT_FORCE_ALLOWED_BRANCHES")
        if raw is None:
            return []
        if isinstance(raw, (list, tuple, set)):
            iterable = raw
        else:
            iterable = str(raw).split(",")
        patterns: list[str] = []
        for entry in iterable:
            text = str(entry).strip()
            if text:
                patterns.append(text)
        return patterns


try:
    from pipeline.env_utils import is_branch_allowed_for_force  # allow-list branch per force push
except ImportError:  # pragma: no cover

    def is_branch_allowed_for_force(branch: str, context: Any, allow_if_unset: bool = True) -> bool:
        patterns = get_force_allowed_branches(context)
        if not patterns:
            return bool(allow_if_unset)
        branch_value = str(branch or "").strip()
        return any(fnmatch(branch_value, str(pattern).strip()) for pattern in patterns if str(pattern).strip())


from pipeline.exceptions import ConfigError, ForcePushError, PipelineError, PushError
from pipeline.file_utils import create_lock_file, remove_lock_file
from pipeline.logging_utils import get_structured_logger, redact_secrets
from pipeline.path_utils import (  # sicurezza path
    ensure_within,
    ensure_within_and_resolve,
    is_safe_subpath,
    iter_safe_paths,
    sorted_paths,
)
from pipeline.proc_utils import CmdError, run_cmd  # âœ… timeout/retry wrapper

# Logger di modulo (fallback); nei flussi reali useremo quello contestualizzato
logger: logging.Logger = get_structured_logger("pipeline.github_utils")

_LEASE_DIRNAME = ".github_push.lockdir"


@runtime_checkable
class _SupportsContext(Protocol):
    """Protocol minimale per il contesto richiesto da queste utility.

    Richiede:
        - slug: str â€” identificativo cliente, usato per naming e logging.
        - md_dir: Path â€” directory che contiene i markdown da pubblicare.
        - env: dict â€” mappa di variabili d'ambiente risolte (opzionale).
        - base_dir: Path â€” base della working area cliente (es. output/timmy-kb-<slug>)
    """

    slug: str
    md_dir: Path
    env: dict[str, Any]
    base_dir: Path


def _is_env_flag_enabled(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _resolve_env_flag(context: _SupportsContext, name: str) -> bool:
    env_map = getattr(context, "env", None)
    if isinstance(env_map, Mapping):
        if name in env_map:
            return _is_env_flag_enabled(env_map.get(name))
    return _is_env_flag_enabled(os.environ.get(name))


def _coerce_positive_float(value: Any, *, default: float, minimum: float) -> float:
    if value is None:
        return default
    try:
        coerced = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if coerced <= 0:
        return max(minimum, default)
    return max(minimum, coerced)


def _resolve_lock_config(context: _SupportsContext) -> dict[str, Any]:
    env_map = getattr(context, "env", {}) or {}
    timeout_default = 10.0
    poll_default = 0.25
    dirname_default = _LEASE_DIRNAME

    timeout_value = env_map.get("TIMMY_GITHUB_LOCK_TIMEOUT_S")
    poll_value = env_map.get("TIMMY_GITHUB_LOCK_POLL_S")
    dirname_value = env_map.get("TIMMY_GITHUB_LOCK_DIRNAME")

    timeout_s = _coerce_positive_float(
        timeout_value if timeout_value is not None else os.environ.get("TIMMY_GITHUB_LOCK_TIMEOUT_S"),
        default=timeout_default,
        minimum=0.1,
    )
    poll_interval_s = _coerce_positive_float(
        poll_value if poll_value is not None else os.environ.get("TIMMY_GITHUB_LOCK_POLL_S"),
        default=poll_default,
        minimum=0.05,
    )
    dirname = (
        str(dirname_value or os.environ.get("TIMMY_GITHUB_LOCK_DIRNAME") or dirname_default).strip() or dirname_default
    )
    return {
        "timeout_s": timeout_s,
        "poll_interval_s": poll_interval_s,
        "dirname": dirname,
    }


def should_push(context: _SupportsContext) -> bool:
    """Determina se il push puï¿½ï¿½ avvenire secondo i flag di sicurezza/env."""
    if _resolve_env_flag(context, "TIMMY_NO_GITHUB"):
        return False
    if _resolve_env_flag(context, "SKIP_GITHUB_PUSH"):
        return False
    return True


class LeaseLock:
    """Lock file-based per evitare push concorrenti sullo stesso workspace."""

    def __init__(
        self,
        base_dir: Path,
        *,
        slug: str,
        logger: logging.Logger | None = None,
        timeout_s: float = 10.0,
        poll_interval_s: float = 0.25,
        dirname: str = _LEASE_DIRNAME,
    ) -> None:
        self._logger = logger or get_structured_logger("pipeline.github_utils.lock")
        self._slug = slug
        self._timeout_s = max(timeout_s, 0.1)
        self._poll_interval_s = max(poll_interval_s, 0.05)
        self._lock_path = ensure_within_and_resolve(base_dir, base_dir / dirname)
        self._acquired = False

    def __enter__(self) -> "LeaseLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()

    def acquire(self) -> None:
        deadline = time.monotonic() + self._timeout_s
        while True:
            try:
                create_lock_file(Path(self._lock_path), payload=f"{os.getpid()}:{time.time():.3f}\n")
                self._acquired = True
                self._logger.debug(
                    "github_utils.lock.acquire",
                    extra={"slug": self._slug, "lock_path": str(self._lock_path)},
                )
                return
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise PushError(
                        "Workspace gia' in uso: lock GitHub attivo. Riprova piu' tardi.",
                        slug=self._slug,
                        file_path=self._lock_path,
                    )
                time.sleep(self._poll_interval_s)
            except ConfigError as exc:
                raise PushError(
                    f"Impossibile creare il lock GitHub: {exc}",
                    slug=self._slug,
                    file_path=self._lock_path,
                ) from exc

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            remove_lock_file(Path(self._lock_path))
            self._logger.debug(
                "github_utils.lock.release",
                extra={"slug": self._slug, "lock_path": str(self._lock_path)},
            )
        except ConfigError as exc:
            self._logger.debug(
                "github_utils.lock.release_failed",
                extra={"slug": self._slug, "lock_path": str(self._lock_path), "error": str(exc)},
            )
        finally:
            self._acquired = False


# ----------------------------
# Helpers generali (env/cmd)
# ----------------------------
def _resolve_default_branch(context: _SupportsContext) -> str:
    """Risoluzione branch di default con fallback a 'main' (SSoT: DEFAULT_GIT_BRANCH_ENV_KEYS)."""
    if getattr(context, "env", None):
        for key in DEFAULT_GIT_BRANCH_ENV_KEYS:
            value = context.env.get(key)
            if isinstance(value, str):
                candidate = value.strip()
                if candidate:
                    return candidate
            elif value is not None:
                candidate = str(value).strip()
                if candidate:
                    return candidate
    for key in DEFAULT_GIT_BRANCH_ENV_KEYS:
        value = get_env_var(key, default=None, required=False)
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
        elif value is not None:
            candidate = str(value).strip()
            if candidate:
                return candidate
    return "main"


def _sanitize_env(*envs: Mapping[str, Any], allow: Optional[Iterable[str]] = None) -> dict[str, str]:
    """
    Costruisce un env sicuro per subprocess:
      - parte da os.environ (str->str),
      - merge dei dizionari passati,
      - scarta chiavi con valore None,
      - converte SEMPRE chiavi e valori in str,
      - se 'allow' Ã¨ specificato, dai dizionari aggiuntivi include SOLO quelle chiavi.
    """
    out: dict[str, str] = dict(os.environ)  # baseline sicura
    allow_set = set(allow or [])

    for env in envs:
        if not env:
            continue
        for k, v in env.items():
            if v is None:
                continue
            sk = str(k)
            if allow and sk not in allow_set:
                continue
            out[sk] = str(v)
    return out


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, Any] | None = None, op: str = "git") -> None:
    """Helper compatibile che delega a run_cmd (con capture attivo per tail diagnostici)."""
    run_cmd(cmd, cwd=str(cwd) if cwd else None, env=env, capture=True, logger=logger, op=op)


def _git_status_porcelain(cwd: Path, env: dict[str, Any] | None = None) -> str:
    """Ritorna l'output di `git status --porcelain`."""
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
    """Ritorna lo SHA (full) per un ref (es.

    HEAD, origin/main).
    """
    cp = run_cmd(
        ["git", "rev-parse", ref],
        cwd=str(cwd),
        env=env,
        capture=True,
        logger=logger,
        op="git rev-parse",
    )
    return (cp.stdout or "").strip()


def _mask_ack(tag: str) -> str:
    """Maschera l'ACK per il logging."""
    if not tag:
        return ""
    if len(tag) <= 4:
        return "***"
    return f"{tag[:2]}â€¦{tag[-2:]}"


# ----------------------------
# Helpers estratti (Patch 5+)
# ----------------------------
def _collect_md_files(book_dir: Path) -> list[Path]:
    """Seleziona file .md validi (no .bak), ricorsivamente, con ordinamento deterministico."""
    md_iter = sorted_paths(
        (
            f
            for f in iter_safe_paths(book_dir, include_dirs=False, include_files=True, suffixes=(".md",))
            if not f.name.endswith(".bak") and is_safe_subpath(f, book_dir)
        ),
        base=book_dir,
    )
    return list(md_iter)


def _ensure_or_create_repo(gh: Github, user: Any, repo_name: str, *, logger: logging.Logger, redact_logs: bool) -> Any:
    """Recupera o crea il repository remoto `repo_name` sotto l'utente/auth corrente.

    Restituisce:
        Oggetto repository (PyGithub), tipizzato come `Any` per compatibilitÃ  runtime.
    """
    try:
        repo = user.get_repo(repo_name)
        msg = f"ðŸ”„ Repository remoto trovato: {repo.full_name}"
        logger.info(redact_secrets(msg) if redact_logs else msg, extra={"repo": repo.full_name})
        return repo
    except GithubException:
        msg = f"âž• Repository non trovato. Creazione di {repo_name}..."
        logger.info(redact_secrets(msg) if redact_logs else msg, extra={"repo": repo_name})
        try:
            repo = user.create_repo(repo_name, private=True)
            msg = f"âœ… Repository creato: {repo.full_name}"
            logger.info(redact_secrets(msg) if redact_logs else msg, extra={"repo": repo.full_name})
            return repo
        except GithubException as e:
            raw = f"Errore durante la creazione del repository {repo_name}: {e}"
            safe = redact_secrets(raw) if redact_logs else raw
            raise PipelineError(safe)


def _prepare_tmp_dir(base_dir: Path) -> Path:
    """Prepara una working dir per il clone **dentro** la base cliente.

    Ritorna un percorso di *clone* (non ancora esistente). Il parent viene creato
    con `mkdtemp`, cosÃ¬ `git clone <url> <dir>` non fallisce per directory giÃ  esistente.
    """
    temp_parent = Path(tempfile.mkdtemp(prefix=".push_", dir=str(base_dir)))
    ensure_within(base_dir, temp_parent)
    clone_dir = temp_parent / "repo"  # non deve esistere al momento del clone
    return clone_dir


def _copy_md_tree(md_files: Sequence[Path], book_dir: Path, dst_root: Path) -> None:
    """Copia i `.md` preservando la struttura, con guardie STRONG sulle destinazioni."""
    for f in md_files:
        dst = dst_root / f.relative_to(book_dir)
        ensure_within(dst_root, dst)  # STRONG
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)


def _stage_and_commit(tmp_dir: Path, env: dict[str, Any] | None, *, commit_msg: str) -> bool:
    """Esegue add/commit se ci sono modifiche.

    Ritorna True se ha committato, False se no-op.
    """
    _run(["git", "add", "-A"], cwd=tmp_dir, env=env, op="git add")
    status = _git_status_porcelain(tmp_dir, env=env)
    if not status.strip():
        return False
    _run(
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
        cwd=tmp_dir,
        env=env,
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
) -> bool:
    """Esegue add/commit e logga il caso no-op. Restituisce True se committato."""
    commit_msg = f"Aggiornamento contenuto KB per cliente {slug}"
    if force_ack:
        commit_msg = f"{commit_msg}\n\nForce-Ack: {force_ack}"
    committed = _stage_and_commit(tmp_dir, env, commit_msg=commit_msg)
    if not committed:
        logger.info(
            "ðŸ“  Nessuna modifica da pubblicare (working dir identica)",
            extra={"slug": slug},
        )
        return False
    return True


def _push_with_retry(
    tmp_dir: Path,
    env: dict[str, Any] | None,
    default_branch: str,
    *,
    logger: logging.Logger,
    redact_logs: bool,
) -> None:
    """Push senza force, con retry singolo dopo `pull --rebase` in caso di rifiuto."""

    def _attempt_push() -> None:
        _run(["git", "push", "origin", default_branch], cwd=tmp_dir, env=env, op="git push")

    try:
        logger.info(f"ðŸ“¤ Push su origin/{default_branch}")
        _attempt_push()
    except CmdError:
        logger.warning("Push rifiutato. Tentativo di sincronizzazione (pull --rebase) e nuovo push...")
        try:
            _run(
                ["git", "pull", "--rebase", "origin", default_branch],
                cwd=tmp_dir,
                env=env,
                op="git pull --rebase",
            )
            _attempt_push()
        except CmdError as e2:
            raw = (
                "Push fallito dopo retry con rebase. "
                "Possibili conflitti tra contenuto locale e remoto. "
                "Suggerimenti: usare un branch dedicato (GIT_DEFAULT_BRANCH) e aprire una PR, "
                "oppure â€” consapevolmente â€” abilitare il force in orchestratore."
            )
            safe = redact_secrets(raw) if redact_logs else raw
            raise PushError(safe) from e2


def _force_push_with_lease(
    tmp_dir: Path,
    env: dict[str, Any] | None,
    default_branch: str,
    force_ack: str,
    *,
    logger: logging.Logger,
    redact_logs: bool,
) -> None:
    """Force push governato con `--force-with-lease` sul ref remoto."""
    # Fetch e calcolo SHA locali/remoti per il lease
    _run(["git", "fetch", "origin", default_branch], cwd=tmp_dir, env=env, op="git fetch")
    remote_sha = _git_rev_parse(f"origin/{default_branch}", cwd=tmp_dir, env=env)
    local_sha = _git_rev_parse("HEAD", cwd=tmp_dir, env=env)

    logger.info(
        "ðŸ“Œ Force push governato (with-lease)",
        extra={
            "branch": default_branch,
            "local_sha": local_sha,
            "remote_sha": remote_sha,
            "force_ack": _mask_ack(force_ack),
        },
    )
    lease_ref = f"refs/heads/{default_branch}:{remote_sha}"
    _run(
        ["git", "push", "--force-with-lease=" + lease_ref, "origin", default_branch],
        cwd=tmp_dir,
        env=env,
        op="git push --force-with-lease",
    )


def _cleanup_tmp_dir(tmp_dir: Path, base_dir: Path) -> None:
    """
    Cleanup working dir temporanea:
    - rimuove la dir di clone,
    - prova a rimuovere anche il genitore temporaneo se creato da `_prepare_tmp_dir`.
    """
    try:
        if isinstance(tmp_dir, Path):
            # rimuovi la dir di clone se esiste
            if tmp_dir.exists():
                ensure_within(base_dir, tmp_dir)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            # prova a rimuovere anche il parent
            parent = tmp_dir.parent
            if parent and parent != base_dir and parent.exists():
                ensure_within(base_dir, parent)
                shutil.rmtree(parent, ignore_errors=True)
    except Exception:
        # Non bloccare l'esecuzione in caso di errore di cleanup
        pass


# ----------------------------
# API pubblica (invariata)
# ----------------------------


def _prepare_repo(
    context: _SupportsContext,
    *,
    github_token: str,
    md_files: Sequence[Path],
    default_branch: str,
    base_dir: Path,
    book_dir: Path,
    redact_logs: bool,
    logger: logging.Logger,
) -> tuple[Any, Path, dict[str, Any]]:
    """Clona il repository remoto, prepara il branch e copia i Markdown locali."""
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
    allowed_from_context = {"GIT_SSH_COMMAND"}
    env = _sanitize_env(
        getattr(context, "env", {}) or {},
        extra_env,
        allow=allowed_from_context.union({"GIT_HTTP_EXTRAHEADER"}),
    )

    logger.info(
        "ðŸš€  Clonazione repo remoto in working dir temporanea",
        extra={"slug": context.slug, "file_path": str(tmp_dir)},
    )

    def _to_bool(value: object) -> bool:
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "on"}

    shallow_env = None
    try:
        shallow_env = (getattr(context, "env", {}) or {}).get("USE_SHALLOW_CLONE")
    except Exception:
        shallow_env = None

    use_shallow = True if shallow_env is None else _to_bool(shallow_env)
    if shallow_env is None:
        env_override = os.environ.get("USE_SHALLOW_CLONE")
        if env_override is not None:
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
            "ðŸ”„  Pull --rebase per sincronizzazione iniziale",
            extra={"slug": context.slug, "branch": default_branch},
        )
        _run(["git", "pull", "--rebase", "origin", default_branch], cwd=tmp_dir, env=env, op="git pull --rebase")
    else:
        _run(["git", "checkout", "-B", default_branch], cwd=tmp_dir, env=env, op="git checkout")

    logger.info(
        "ðŸ§¹ Preparazione contenuti da book/",
        extra={"slug": context.slug, "file_path": str(book_dir)},
    )
    _copy_md_tree(md_files, book_dir, tmp_dir)

    return repo, tmp_dir, env


def push_output_to_github(
    context: _SupportsContext,
    *,
    github_token: str,
    do_push: bool = True,
    # governance del force (no I/O qui)
    force_push: bool = False,
    force_ack: str | None = None,
    redact_logs: bool = False,
) -> None:
    """Esegue il push dei file `.md` presenti nella cartella `book` del cliente su GitHub."""
    local_logger = get_structured_logger("pipeline.github_utils", context=context)

    global logger
    logger = local_logger

    if not github_token:
        raise PipelineError(
            "GITHUB_TOKEN mancante o vuoto: impossibile eseguire push.",
            slug=getattr(context, "slug", None),
        )

    if not should_push(context):
        local_logger.info(
            "Push GitHub disabilitato da variabili d'ambiente (TIMMY_NO_GITHUB/SKIP_GITHUB_PUSH).",
            extra={"slug": context.slug},
        )
        return

    book_dir = context.md_dir
    if not book_dir.exists():
        raise PipelineError(
            f"Cartella book non trovata: {book_dir}",
            slug=context.slug,
            file_path=book_dir,
        )

    base_dir = getattr(context, "base_dir", None)
    if not base_dir:
        raise PipelineError("Context.base_dir assente: impossibile determinare la working area.", slug=context.slug)
    try:
        ensure_within(base_dir, book_dir)
    except Exception:
        raise PipelineError(
            f"Percorso book non sicuro: {book_dir} (fuori da {base_dir})",
            slug=context.slug,
            file_path=book_dir,
        )

    md_files = _collect_md_files(book_dir)
    if not md_files:
        msg = "ðŸ›‘ Nessun file .md valido trovato nella cartella book. Push annullato."
        local_logger.warning(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return

    if do_push is False:
        msg = "Push disattivato: do_push=False (dry run a carico dell'orchestratore)."
        local_logger.info(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return

    default_branch = _resolve_default_branch(context)
    local_logger.info(
        f"ðŸš§ Preparazione push su GitHub (branch: {default_branch})",
        extra={"slug": context.slug, "branch": default_branch},
    )
    lock_config = _resolve_lock_config(context)
    lock = LeaseLock(base_dir, slug=context.slug, logger=local_logger, **lock_config)
    lock.acquire()

    repo = None
    tmp_dir: Path | None = None
    env: dict[str, Any] | None = None
    try:
        repo, tmp_dir, env = _prepare_repo(
            context,
            github_token=github_token,
            md_files=md_files,
            default_branch=default_branch,
            base_dir=base_dir,
            book_dir=book_dir,
            redact_logs=redact_logs,
            logger=local_logger,
        )

        committed = _stage_changes(
            tmp_dir,
            env,
            slug=context.slug,
            force_ack=force_ack,
            logger=local_logger,
        )
        if not committed:
            return

        if force_push:
            if not force_ack:
                raise ForcePushError(
                    "Force push richiesto senza ACK. Serve force_ack valorizzato.",
                    slug=context.slug,
                )
            if not is_branch_allowed_for_force(default_branch, context, allow_if_unset=True):
                patterns = get_force_allowed_branches(context)
                patterns_str = ", ".join(patterns) if patterns else "(lista vuota)"
                raise ForcePushError(
                    f"Force push NON consentito sul branch '{default_branch}'. "
                    f"Branch ammessi (GIT_FORCE_ALLOWED_BRANCHES): {patterns_str}",
                    slug=context.slug,
                )

            _force_push_with_lease(
                tmp_dir,
                env,
                default_branch,
                force_ack,
                logger=local_logger,
                redact_logs=redact_logs,
            )
        else:
            _push_with_retry(tmp_dir, env, default_branch, logger=local_logger, redact_logs=redact_logs)

        local_logger.info(
            f"ðŸ“¦ Push completato su {repo.full_name} ({default_branch})",
            extra={"slug": context.slug, "repo": repo.full_name, "branch": default_branch},
        )
    except CmdError as e:
        tail = (e.stderr or e.stdout or "").strip()
        tail = tail[-2000:] if tail else ""
        raw = f"Errore Git: {e.op or 'git'} (tentativo {e.attempt}/{e.attempts}) â†’ {tail}"
        safe = redact_secrets(raw) if redact_logs else raw
        raise PushError(safe, slug=context.slug) from e
    finally:
        lock.release()
        if tmp_dir is not None:
            _cleanup_tmp_dir(tmp_dir, base_dir)
