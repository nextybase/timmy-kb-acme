# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/github_utils.py
"""
Utility GitHub per la pipeline Timmy-KB.

Cosa fa
-------
- **Rileva o crea** il repository remoto del cliente (`timmy-kb-<slug>`).
- **Pubblica** i soli file Markdown presenti in `book/` (escludendo `.bak`), preservando l’albero.
- **Gestisce il branch di default** con una SSoT di chiavi d’ambiente (`DEFAULT_GIT_BRANCH_ENV_KEYS`).
- **Esegue push incrementale** con retry (pull --rebase → nuovo push) oppure
  **force push governato** (`--force-with-lease`) con allow-list di branch e `force_ack`.
- **Sicurezza path**: STRONG guard con `ensure_within` per tutte le scritture/cancellezioni.
- **Credenziali via env**: header HTTP Basic in `GIT_HTTP_EXTRAHEADER` (il token non compare nei comandi).
- **Working dir temporanea sicura** sotto la base cliente:
  il clone avviene in una sottocartella **non esistente** (evita il classico errore di `git clone` in dir già presente).

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
from pathlib import Path
from typing import Protocol, runtime_checkable, Mapping, Iterable, Any, Optional, Sequence

from github import Github
from github.GithubException import GithubException

from pipeline.logging_utils import redact_secrets, get_structured_logger
from pipeline.exceptions import PipelineError, ForcePushError, PushError
from pipeline.path_utils import (
    is_safe_subpath,
    ensure_within,
    sorted_paths,
)  # sicurezza path + ordinamento deterministico
from pipeline.env_utils import (
    get_env_var,  # 🔐 env resolver (no masking qui)
    is_branch_allowed_for_force,  # ✅ allow-list branch per force push
    get_force_allowed_branches,  # ✅ per log/errore esplicativo
)
from pipeline.constants import DEFAULT_GIT_BRANCH_ENV_KEYS
from pipeline.proc_utils import run_cmd, CmdError  # ✅ timeout/retry wrapper


# Logger di modulo (fallback); nei flussi reali useremo quello contestualizzato
logger: logging.Logger = get_structured_logger("pipeline.github_utils")


@runtime_checkable
class _SupportsContext(Protocol):
    """Protocol minimale per il contesto richiesto da queste utility.

    Richiede:
        - slug: str — identificativo cliente, usato per naming e logging.
        - md_dir: Path — directory che contiene i markdown da pubblicare.
        - env: dict — mappa di variabili d'ambiente risolte (opzionale).
        - base_dir: Path — base della working area cliente (es. output/timmy-kb-<slug>)
    """

    slug: str
    md_dir: Path
    env: dict
    base_dir: Path


# ----------------------------
# Helpers generali (env/cmd)
# ----------------------------
def _resolve_default_branch(context: _SupportsContext) -> str:
    """Risoluzione branch di default con fallback a 'main' (SSoT: DEFAULT_GIT_BRANCH_ENV_KEYS)."""
    # 1) variabili nel contesto (preferite)
    if getattr(context, "env", None):
        for key in DEFAULT_GIT_BRANCH_ENV_KEYS:
            br = context.env.get(key)
            if br:
                return br
    # 2) variabili d'ambiente tramite resolver centralizzato
    for key in DEFAULT_GIT_BRANCH_ENV_KEYS:
        br = get_env_var(key, default=None, required=False)
        if br:
            return br
    # 3) fallback sicuro
    return "main"


def _sanitize_env(
    *envs: Mapping[str, Any], allow: Optional[Iterable[str]] = None
) -> dict[str, str]:
    """
    Costruisce un env sicuro per subprocess:
      - parte da os.environ (str->str),
      - merge dei dizionari passati,
      - scarta chiavi con valore None,
      - converte SEMPRE chiavi e valori in str,
      - se 'allow' è specificato, dai dizionari aggiuntivi include SOLO quelle chiavi.
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


def _run(
    cmd: list[str], *, cwd: Path | None = None, env: dict | None = None, op: str = "git"
) -> None:
    """Helper compatibile che delega a run_cmd (con capture attivo per tail diagnostici)."""
    run_cmd(cmd, cwd=str(cwd) if cwd else None, env=env, capture=True, logger=logger, op=op)


def _git_status_porcelain(cwd: Path, env: dict | None = None) -> str:
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


def _git_rev_parse(ref: str, cwd: Path, env: dict | None = None) -> str:
    """Ritorna lo SHA (full) per un ref (es. HEAD, origin/main)."""
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
    return f"{tag[:2]}…{tag[-2:]}"


# ----------------------------
# Helpers estratti (Patch 5+)
# ----------------------------
def _collect_md_files(book_dir: Path) -> list[Path]:
    """Seleziona file .md validi (no .bak), ricorsivamente, con ordinamento deterministico."""
    md_files = sorted_paths(
        (
            f
            for f in book_dir.rglob("*.md")
            if not f.name.endswith(".bak") and is_safe_subpath(f, book_dir)
        ),
        base=book_dir,
    )
    return md_files


def _ensure_or_create_repo(
    gh: Github, user, repo_name: str, *, logger: logging.Logger, redact_logs: bool
) -> Any:
    """Recupera o crea il repository remoto `repo_name` sotto l'utente/auth corrente.

    Restituisce:
        Oggetto repository (PyGithub), tipizzato come `Any` per compatibilità runtime.
    """
    try:
        repo = user.get_repo(repo_name)
        msg = f"🔄 Repository remoto trovato: {repo.full_name}"
        logger.info(redact_secrets(msg) if redact_logs else msg, extra={"repo": repo.full_name})
        return repo
    except GithubException:
        msg = f"➕ Repository non trovato. Creazione di {repo_name}..."
        logger.info(redact_secrets(msg) if redact_logs else msg, extra={"repo": repo_name})
        try:
            repo = user.create_repo(repo_name, private=True)
            msg = f"✅ Repository creato: {repo.full_name}"
            logger.info(redact_secrets(msg) if redact_logs else msg, extra={"repo": repo.full_name})
            return repo
        except GithubException as e:
            raw = f"Errore durante la creazione del repository {repo_name}: {e}"
            safe = redact_secrets(raw) if redact_logs else raw
            raise PipelineError(safe)


def _prepare_tmp_dir(base_dir: Path) -> Path:
    """
    Prepara una working dir per il clone **dentro** la base cliente.

    Ritorna un percorso di *clone* (non ancora esistente). Il parent viene creato
    con `mkdtemp`, così `git clone <url> <dir>` non fallisce per directory già esistente.
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


def _stage_and_commit(tmp_dir: Path, env: dict | None, *, commit_msg: str) -> bool:
    """Esegue add/commit se ci sono modifiche. Ritorna True se ha committato, False se no-op."""
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


def _push_with_retry(
    tmp_dir: Path,
    env: dict | None,
    default_branch: str,
    *,
    logger: logging.Logger,
    redact_logs: bool,
) -> None:
    """Push senza force, con retry singolo dopo `pull --rebase` in caso di rifiuto."""

    def _attempt_push() -> None:
        _run(["git", "push", "origin", default_branch], cwd=tmp_dir, env=env, op="git push")

    try:
        logger.info(f"📤 Push su origin/{default_branch}")
        _attempt_push()
    except CmdError:
        logger.warning(
            "⚠️  Push rifiutato. Tentativo di sincronizzazione (pull --rebase) e nuovo push..."
        )
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
                "oppure — consapevolmente — abilitare il force in orchestratore."
            )
            safe = redact_secrets(raw) if redact_logs else raw
            raise PushError(safe) from e2


def _force_push_with_lease(
    tmp_dir: Path,
    env: dict | None,
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
        "📌 Force push governato (with-lease)",
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
    # === Logger contestualizzato (slug/run_id/redaction filter) ===
    local_logger = get_structured_logger("pipeline.github_utils", context=context)

    # (NUOVO) Allinea il logger di modulo a quello contestualizzato
    # per far sì che anche gli helper (_run/_git_*) logghino con lo stesso contesto.
    global logger
    logger = local_logger

    # Validazione basilare prerequisiti
    if not github_token:
        raise PipelineError(
            "GITHUB_TOKEN mancante o vuoto: impossibile eseguire push.",
            slug=getattr(context, "slug", None),
        )

    book_dir = context.md_dir
    if not book_dir.exists():
        raise PipelineError(
            f"Cartella book non trovata: {book_dir}",
            slug=context.slug,
            file_path=book_dir,
        )

    # Guard-rail: directory dentro la base del cliente (STRONG)
    base_dir = getattr(context, "base_dir", None)
    if not base_dir:
        raise PipelineError(
            "Context.base_dir assente: impossibile determinare la working area.", slug=context.slug
        )
    try:
        ensure_within(base_dir, book_dir)
    except Exception:
        raise PipelineError(
            f"Percorso book non sicuro: {book_dir} (fuori da {base_dir})",
            slug=context.slug,
            file_path=book_dir,
        )

    # Selezione file `.md` validi
    md_files = _collect_md_files(book_dir)
    if not md_files:
        msg = "⚠️ Nessun file .md valido trovato nella cartella book. Push annullato."
        local_logger.warning(
            redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug}
        )
        return

    if do_push is False:
        msg = "Push disattivato: do_push=False (dry run a carico dell'orchestratore)."
        local_logger.info(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return

    default_branch = _resolve_default_branch(context)
    local_logger.info(
        f"📤 Preparazione push su GitHub (branch: {default_branch})",
        extra={"slug": context.slug, "branch": default_branch},
    )

    # Autenticazione GitHub via SDK (per ensure repo) + URL remota
    gh = Github(github_token)
    try:
        user = gh.get_user()
    except GithubException as e:
        raw = f"Errore autenticazione GitHub: {e}"
        safe = redact_secrets(raw) if redact_logs else raw
        raise PipelineError(safe, slug=context.slug)

    repo_name = f"timmy-kb-{context.slug}"
    repo = _ensure_or_create_repo(gh, user, repo_name, logger=local_logger, redact_logs=redact_logs)
    remote_url = repo.clone_url  # https://github.com/<owner>/<repo>.git

    # Working dir temporanea **dentro** la base del cliente (clone in dir non esistente)
    tmp_dir = _prepare_tmp_dir(base_dir)

    # Preparo env con header http basic per autenticazione su clone/pull/push
    header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
    extra_env = {"GIT_HTTP_EXTRAHEADER": f"Authorization: Basic {header}"}
    allowed_from_context = {"GIT_SSH_COMMAND"}
    env = _sanitize_env(
        getattr(context, "env", {}) or {},
        extra_env,
        allow=allowed_from_context.union({"GIT_HTTP_EXTRAHEADER"}),
    )

    try:
        # Clone e checkout/creazione branch
        local_logger.info(
            "⬇️  Clonazione repo remoto in working dir temporanea",
            extra={"slug": context.slug, "file_path": str(tmp_dir)},
        )
        _run(["git", "clone", remote_url, str(tmp_dir)], env=env, op="git clone")

        # Determina se il branch esiste sul remoto
        exists_remote_branch = True
        try:
            run_cmd(
                ["git", "rev-parse", f"origin/{default_branch}"],
                cwd=str(tmp_dir),
                env=env,
                capture=True,
                logger=local_logger,
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
            local_logger.info(
                "↕️  Pull --rebase per sincronizzazione iniziale",
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

        # Copia contenuti .md da book/ nella working dir clonata (STRONG sui dst)
        local_logger.info(
            "🧩 Preparazione contenuti da book/",
            extra={"slug": context.slug, "file_path": str(book_dir)},
        )
        _copy_md_tree(md_files, book_dir, tmp_dir)

        # Stage e commit
        commit_msg = f"Aggiornamento contenuto KB per cliente {context.slug}"
        if force_ack:
            commit_msg = f"{commit_msg}\n\nForce-Ack: {force_ack}"
        committed = _stage_and_commit(tmp_dir, env, commit_msg=commit_msg)
        if not committed:
            local_logger.info(
                "ℹ️  Nessuna modifica da pubblicare (working dir identica)",
                extra={"slug": context.slug},
            )
            return

        # Ramo di push: incrementale (default) o force governato
        if force_push:
            if not force_ack:
                raise ForcePushError(
                    "Force push richiesto senza ACK. Contratto violato: serve force_ack valorizzato.",
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
            _push_with_retry(
                tmp_dir, env, default_branch, logger=local_logger, redact_logs=redact_logs
            )

        local_logger.info(
            f"✅ Push completato su {repo.full_name} ({default_branch})",
            extra={"slug": context.slug, "repo": repo.full_name, "branch": default_branch},
        )

    except CmdError as e:
        # Fallimenti generici di git → PushError con messaggio compattato
        tail = (e.stderr or e.stdout or "").strip()
        tail = tail[-2000:] if tail else ""
        raw = f"Errore Git: {e.op or 'git'} (tentativo {e.attempt}/{e.attempts}) → {tail}"
        safe = redact_secrets(raw) if redact_logs else raw
        raise PushError(safe, slug=context.slug) from e
    finally:
        _cleanup_tmp_dir(tmp_dir, base_dir)
