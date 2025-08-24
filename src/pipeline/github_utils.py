# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/github_utils.py
"""
Utility per interagire con GitHub:
- Creazione/rilevamento repo cliente
- Push incrementale del contenuto della cartella 'book' (solo file .md, esclusi .bak)
- Branch di default configurabile via (in ordine di priorità):
    1) context.env["GIT_DEFAULT_BRANCH"] o context.env["GITHUB_BRANCH"]
    2) variabili lette tramite resolver centralizzato (env_utils.get_env_var)
    3) fallback "main"

Note architetturali (v1.1+):
- Nessuna interattività in questo modulo (niente prompt/input). Le decisioni di
  conferma push sono responsabilità degli orchestratori (CLI/UX).
- Push **incrementale** di default (no --force). In caso di rifiuto non-fast-forward
  effettuiamo un `pull --rebase` e ritentiamo una volta. Se emergono conflitti, alziamo errore.
- Fase 2: uso di `proc_utils.run_cmd` con timeout/retry e log strutturati.
  Gli errori di `git` sono mappati su `PushError` con messaggi compatti (stderr tail).

Sicurezza:
- Path-safety: convalida dei percorsi con `is_safe_subpath`.
- Token: header HTTP Basic passato via env `GIT_HTTP_EXTRAHEADER` (non compare nel comando).
"""

from __future__ import annotations

import base64
import os
import shutil
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable, Mapping, Iterable, Any, Optional

from github import Github
from github.GithubException import GithubException

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError, ForcePushError, PushError
from pipeline.path_utils import is_safe_subpath, sorted_paths  # sicurezza path + ordinamento deterministico
from pipeline.env_utils import (
    redact_secrets,
    get_env_var,                       # 🔐 redazione + env resolver
    is_branch_allowed_for_force,       # ✅ allow-list branch per force push
    get_force_allowed_branches,        # ✅ per log/errore esplicativo
)
from pipeline.proc_utils import run_cmd, CmdError  # ✅ timeout/retry wrapper

# Logger di modulo (fallback); nei flussi reali usiamo quello contestualizzato
logger = get_structured_logger("pipeline.github_utils")


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


def _resolve_default_branch(context: _SupportsContext) -> str:
    """Risoluzione branch di default con fallback a 'main'."""
    # 1) variabili nel contesto (preferite)
    if getattr(context, "env", None):
        br = context.env.get("GIT_DEFAULT_BRANCH") or context.env.get("GITHUB_BRANCH")
        if br:
            return br
    # 2) variabili d'ambiente tramite resolver centralizzato
    br = get_env_var("GIT_DEFAULT_BRANCH", default=None, required=False) or get_env_var(
        "GITHUB_BRANCH", default=None, required=False
    )
    if br:
        return br
    # 3) fallback sicuro
    return "main"


# ----------------------------
# Env sanitization
# ----------------------------

def _sanitize_env(
    *envs: Mapping[str, Any],
    allow: Optional[Iterable[str]] = None,
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


# ----------------------------
# Wrappers git (proc_utils)
# ----------------------------

def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None, op: str = "git") -> None:
    """Helper compatibile che delega a run_cmd (con capture attivo per tail diagnostici)."""
    run_cmd(cmd, cwd=str(cwd) if cwd else None, env=env, capture=True, logger=logger, op=op)


def _git_status_porcelain(cwd: Path, env: dict | None = None) -> str:
    """Ritorna l'output di `git status --porcelain`."""
    cp = run_cmd(["git", "status", "--porcelain"], cwd=str(cwd), env=env, capture=True, logger=logger, op="git status")
    return cp.stdout or ""


def _git_rev_parse(ref: str, cwd: Path, env: dict | None = None) -> str:
    """Ritorna lo SHA (full) per un ref (es. HEAD, origin/main)."""
    cp = run_cmd(["git", "rev-parse", ref], cwd=str(cwd), env=env, capture=True, logger=logger, op="git rev-parse")
    return (cp.stdout or "").strip()


def _mask_ack(tag: str) -> str:
    """Maschera l'ACK per il logging."""
    if not tag:
        return ""
    if len(tag) <= 4:
        return "***"
    return f"{tag[:2]}…{tag[-2:]}"


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

    # Guard-rail: directory dentro la base del cliente
    base_dir = getattr(context, "base_dir", None)
    if not base_dir:
        raise PipelineError("Context.base_dir assente: impossibile determinare la working area.", slug=context.slug)

    if not is_safe_subpath(book_dir, base_dir):
        raise PipelineError(
            f"Percorso book non sicuro: {book_dir} (fuori da {base_dir})",
            slug=context.slug,
            file_path=book_dir,
        )

    # Seleziona file .md validi (path-safety) ricorsivamente — ordinamento deterministico
    md_files = sorted_paths(
        (f for f in book_dir.rglob("*.md") if not f.name.endswith(".bak") and is_safe_subpath(f, book_dir)),
        base=book_dir,
    )
    if not md_files:
        msg = "⚠️ Nessun file .md valido trovato nella cartella book. Push annullato."
        local_logger.warning(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return

    if do_push is False:
        msg = "Push disattivato: do_push=False (dry run a carico dell'orchestratore)."
        local_logger.info(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return

    default_branch = _resolve_default_branch(context)
    msg = f"📤 Preparazione push su GitHub (branch: {default_branch})"
    local_logger.info(
        redact_secrets(msg) if redact_logs else msg,
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

    # Recupera o crea repo remoto
    try:
        repo = user.get_repo(repo_name)
        msg = f"🔄 Repository remoto trovato: {repo.full_name}"
        local_logger.info(
            redact_secrets(msg) if redact_logs else msg,
            extra={"slug": context.slug, "repo": repo.full_name, "branch": default_branch},
        )
    except GithubException:
        msg = f"➕ Repository non trovato. Creazione di {repo_name}..."
        local_logger.info(
            redact_secrets(msg) if redact_logs else msg,
            extra={"slug": context.slug, "repo": repo_name, "branch": default_branch},
        )
        try:
            repo = user.create_repo(repo_name, private=True)
            msg = f"✅ Repository creato: {repo.full_name}"
            local_logger.info(
                redact_secrets(msg) if redact_logs else msg,
                extra={"slug": context.slug, "repo": repo.full_name, "branch": default_branch},
            )
        except GithubException as e:
            raw = f"Errore durante la creazione del repository {repo_name}: {e}"
            safe = redact_secrets(raw) if redact_logs else raw
            raise PipelineError(safe, slug=context.slug)

    remote_url = repo.clone_url  # https://github.com/<org>/<repo>.git

    # Cartella temporanea **dentro** output/timmy-kb-<slug>
    tmp_dir = Path(tempfile.mkdtemp(prefix=".push_", dir=str(base_dir)))
    if not is_safe_subpath(tmp_dir, base_dir):
        raise PipelineError(
            f"Working dir temporanea fuori dalla base consentita: {tmp_dir}",
            slug=context.slug,
            file_path=tmp_dir,
        )

    # Preparo env con header http basic per autenticazione su clone/pull/push
    header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
    extra_env = {
        "GIT_HTTP_EXTRAHEADER": f"Authorization: Basic {header}",
    }
    # ✅ includi solo chiavi strettamente necessarie da context.env
    allowed_from_context = {"GIT_SSH_COMMAND"}
    env = _sanitize_env(
        getattr(context, "env", {}) or {},
        extra_env,
        allow=allowed_from_context.union({"GIT_HTTP_EXTRAHEADER"})
    )

    try:
        # Clone e checkout/creazione branch
        local_logger.info(
            "⬇️  Clonazione repo remoto in working dir temporanea",
            extra={"slug": context.slug, "file_path": str(tmp_dir)},
        )
        _run(["git", "clone", remote_url, str(tmp_dir)], env=env, op="git clone")

        # Determina se il branch esiste sul remoto
        exists_remote_branch = False
        try:
            run_cmd(
                ["git", "rev-parse", f"origin/{default_branch}"],
                cwd=str(tmp_dir),
                env=env,
                capture=True,
                logger=local_logger,
                op="git rev-parse",
            )
            exists_remote_branch = True
        except CmdError:
            exists_remote_branch = False

        if exists_remote_branch:
            _run(["git", "checkout", "-B", default_branch, f"origin/{default_branch}"], cwd=tmp_dir, env=env, op="git checkout")
        else:
            _run(["git", "checkout", "-B", default_branch], cwd=tmp_dir, env=env, op="git checkout")

        # Sync iniziale
        if exists_remote_branch:
            local_logger.info("↕️  Pull --rebase per sincronizzazione iniziale", extra={"slug": context.slug, "branch": default_branch})
            _run(["git", "pull", "--rebase", "origin", default_branch], cwd=tmp_dir, env=env, op="git pull --rebase")

        # Copia contenuti .md da book/ nella working dir clonata
        local_logger.info("🧩 Preparazione contenuti da book/", extra={"slug": context.slug, "file_path": str(book_dir)})
        for f in md_files:
            dst = tmp_dir / f.relative_to(book_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

        # Stage e commit se necessario
        _run(["git", "add", "-A"], cwd=tmp_dir, env=env, op="git add")
        status = _git_status_porcelain(tmp_dir, env=env)
        if not status.strip():
            local_logger.info("ℹ️  Nessuna modifica da pubblicare (working dir identica)", extra={"slug": context.slug})
            return

        # Commit message (aggiunge trailer Force-Ack se presente)
        commit_msg = f"Aggiornamento contenuto KB per cliente {context.slug}"
        if force_ack:
            commit_msg = f"{commit_msg}\n\nForce-Ack: {force_ack}"

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

        # Ramo di push: incrementale (default) o force governato
        if force_push:
            if not force_ack:
                raise ForcePushError(
                    "Force push richiesto senza ACK. Contratto violato: serve force_ack valorizzato.",
                    slug=context.slug,
                )

            # ✅ Allow-list dei branch per force push
            if not is_branch_allowed_for_force(default_branch, context, allow_if_unset=True):
                patterns = get_force_allowed_branches(context)
                patterns_str = ", ".join(patterns) if patterns else "(lista vuota)"
                raise ForcePushError(
                    f"Force push NON consentito sul branch '{default_branch}'. "
                    f"Branch ammessi (GIT_FORCE_ALLOWED_BRANCHES): {patterns_str}",
                    slug=context.slug,
                )

            # Fetch e calcolo SHA locali/remoti per il lease
            _run(["git", "fetch", "origin", default_branch], cwd=tmp_dir, env=env, op="git fetch")
            remote_sha = _git_rev_parse(f"origin/{default_branch}", cwd=tmp_dir, env=env)
            local_sha = _git_rev_parse("HEAD", cwd=tmp_dir, env=env)

            # Logging strutturato del ramo force (ack mascherato)
            local_logger.info(
                "📌 Force push governato (with-lease)",
                extra={
                    "slug": context.slug,
                    "branch": default_branch,
                    "local_sha": local_sha,
                    "remote_sha": remote_sha,
                    "force_ack": _mask_ack(force_ack),
                },
            )

            # Push con lease esplicito sul ref remoto
            lease_ref = f"refs/heads/{default_branch}:{remote_sha}"
            _run(
                ["git", "push", "--force-with-lease=" + lease_ref, "origin", default_branch],
                cwd=tmp_dir,
                env=env,
                op="git push --force-with-lease",
            )
        else:
            # Push (no force) + retry con rebase se rifiutato
            def _attempt_push() -> None:
                _run(["git", "push", "origin", default_branch], cwd=tmp_dir, env=env, op="git push")

            try:
                local_logger.info(f"📤 Push su origin/{default_branch}", extra={"slug": context.slug, "branch": default_branch})
                _attempt_push()
            except CmdError:
                # Ritenta una volta con rebase (conflitti -> fallisce)
                local_logger.warning(
                    "⚠️  Push rifiutato. Tentativo di sincronizzazione (pull --rebase) e nuovo push...",
                    extra={"slug": context.slug, "branch": default_branch},
                )
                try:
                    _run(["git", "pull", "--rebase", "origin", default_branch], cwd=tmp_dir, env=env, op="git pull --rebase")
                    _attempt_push()
                except CmdError as e2:
                    raw = (
                        "Push fallito dopo retry con rebase. "
                        "Possibili conflitti tra contenuto locale e remoto. "
                        "Suggerimenti: usare un branch dedicato (GIT_DEFAULT_BRANCH) e aprire una PR, "
                        "oppure — consapevolmente — abilitare il force in orchestratore."
                    )
                    safe = redact_secrets(raw) if redact_logs else raw
                    raise PushError(safe, slug=context.slug) from e2

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
        # Cleanup working dir temporanea
        try:
            if tmp_dir.exists() and is_safe_subpath(tmp_dir, base_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            # Non bloccare l'esecuzione in caso di errore di cleanup
            pass
