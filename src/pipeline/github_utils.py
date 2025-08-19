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

Sicurezza:
- Path-safety: convalida dei percorsi con `is_safe_subpath`.
- Token: header HTTP Basic passato via env `GIT_HTTP_EXTRAHEADER` (non compare nel comando).
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from github import Github
from github.GithubException import GithubException

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError
from pipeline.path_utils import is_safe_subpath  # sicurezza path
from pipeline.env_utils import redact_secrets, get_env_var  # 🔐 redazione + env resolver

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
    """Risoluzione branch di default con fallback a 'main'.

    Ordine di priorità:
      1) `context.env["GIT_DEFAULT_BRANCH"]` o `context.env["GITHUB_BRANCH"]` (se presenti)
      2) variabili di processo risolte con env_utils.get_env_var
      3) fallback sicuro: `"main"`
    """
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


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    """Helper per subprocess.run con check=True e logging essenziale."""
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, env=env)


def _git_status_porcelain(cwd: Path, env: dict | None = None) -> str:
    """Ritorna l'output di `git status --porcelain`."""
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(cwd),
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )
    return proc.stdout or ""


def push_output_to_github(
    context: _SupportsContext,
    *,
    github_token: str,
    do_push: bool = True,
    redact_logs: bool = False,
) -> None:
    """Esegue il push **incrementale** dei file `.md` presenti nella cartella `book` del cliente su GitHub.

    Strategia:
    - `git clone` del repo remoto in una cartella temporanea **dentro** `output/timmy-kb-<slug>`
    - checkout (o creazione) del branch di lavoro
    - `git pull --rebase` per sincronizzarsi con il remoto
    - copia dei `.md` da `book/` nella working dir clonata
    - `git add -A` → commit se ci sono modifiche → `git push` (no --force)
    - retry singolo in caso di rifiuto non-fast-forward con ulteriore `pull --rebase`

    Args:
        context: Contesto con attributi `slug`, `md_dir`, `base_dir` e (opz.) `env`.
        github_token: Token personale GitHub (PAT). Deve essere valorizzato.
        do_push: Se `False`, NON esegue il push (dry-run controllato dall'orchestratore).
        redact_logs: Se `True`, applica redazione ai messaggi di errore/log potenzialmente sensibili.

    Raises:
        PipelineError: Se prerequisiti mancanti (cartella o token) o in caso di errori push/creazione repo.
    """
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

    # Seleziona file .md validi (path-safety) ricorsivamente
    md_files = sorted(
        f
        for f in book_dir.rglob("*.md")
        if not f.name.endswith(".bak") and is_safe_subpath(f, book_dir)
    )
    if not md_files:
        msg = "⚠️ Nessun file .md valido trovato nella cartella book. Push annullato."
        logger.warning(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return

    if do_push is False:
        msg = "Push disattivato: do_push=False (dry run a carico dell'orchestratore)."
        logger.info(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return

    default_branch = _resolve_default_branch(context)
    msg = f"📤 Preparazione push incrementale su GitHub (branch: {default_branch})"
    logger.info(
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
        logger.info(
            redact_secrets(msg) if redact_logs else msg,
            extra={"slug": context.slug, "repo": repo.full_name, "branch": default_branch},
        )
    except GithubException:
        msg = f"➕ Repository non trovato. Creazione di {repo_name}..."
        logger.info(
            redact_secrets(msg) if redact_logs else msg,
            extra={"slug": context.slug, "repo": repo_name, "branch": default_branch},
        )
        try:
            repo = user.create_repo(repo_name, private=True)
            msg = f"✅ Repository creato: {repo.full_name}"
            logger.info(
                redact_secrets(msg) if redact_logs else msg,
                extra={"slug": context.slug, "repo": repo.full_name, "branch": default_branch},
            )
        except GithubException as e:
            raw = f"Errore durante la creazione del repository {repo_name}: {e}"
            safe = redact_secrets(raw) if redact_logs else raw
            raise PipelineError(safe, slug=context.slug)

    remote_url = repo.clone_url  # https://github.com/<org>/<repo>.git

    # Cartella temporanea **dentro** output/timmy-kb-<slug>
    # Uso mkdtemp con dir=base_dir per garantire path interno controllato.
    tmp_dir = Path(tempfile.mkdtemp(prefix=".push_", dir=str(base_dir)))
    if not is_safe_subpath(tmp_dir, base_dir):
        # Ultra-cautela: non dovrebbe mai accadere
        raise PipelineError(
            f"Working dir temporanea fuori dalla base consentita: {tmp_dir}",
            slug=context.slug,
            file_path=tmp_dir,
        )

    # Preparo env con header http basic per autenticazione su clone/pull/push
    header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
    env = os.environ.copy()
    env["GIT_HTTP_EXTRAHEADER"] = f"Authorization: Basic {header}"

    try:
        # Clone e checkout/creazione branch
        logger.info("⬇️  Clonazione repo remoto in working dir temporanea", extra={"slug": context.slug, "file_path": tmp_dir})
        _run(["git", "clone", remote_url, str(tmp_dir)], env=env)

        # Determina se il branch esiste sul remoto
        exists_remote_branch = False
        try:
            subprocess.run(
                ["git", "rev-parse", f"origin/{default_branch}"],
                cwd=str(tmp_dir),
                check=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            exists_remote_branch = True
        except subprocess.CalledProcessError:
            exists_remote_branch = False

        if exists_remote_branch:
            _run(["git", "checkout", "-B", default_branch, f"origin/{default_branch}"], cwd=tmp_dir, env=env)
        else:
            _run(["git", "checkout", "-B", default_branch], cwd=tmp_dir, env=env)

        # Sync iniziale
        if exists_remote_branch:
            logger.info("↕️  Pull --rebase per sincronizzazione iniziale", extra={"slug": context.slug, "branch": default_branch})
            _run(["git", "pull", "--rebase", "origin", default_branch], cwd=tmp_dir, env=env)

        # Copia contenuti .md da book/ nella working dir clonata
        logger.info("🧩 Preparazione contenuti da book/", extra={"slug": context.slug, "file_path": str(book_dir)})
        for f in md_files:
            dst = tmp_dir / f.relative_to(book_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

        # Stage e commit se necessario
        _run(["git", "add", "-A"], cwd=tmp_dir, env=env)
        status = _git_status_porcelain(tmp_dir, env=env)
        if not status.strip():
            logger.info("ℹ️  Nessuna modifica da pubblicare (working dir identica)", extra={"slug": context.slug})
            return

        commit_msg = f"Aggiornamento contenuto KB per cliente {context.slug}"
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
        )

        # Push (no force) + retry con rebase se rifiutato
        def _attempt_push() -> None:
            _run(["git", "push", "origin", default_branch], cwd=tmp_dir, env=env)

        try:
            logger.info("📤 Push su origin/%s", default_branch, extra={"slug": context.slug, "branch": default_branch})
            _attempt_push()
        except subprocess.CalledProcessError as e1:
            # Ritenta una volta con rebase (conflitti -> fallisce)
            logger.warning(
                "⚠️  Push rifiutato. Tentativo di sincronizzazione (pull --rebase) e nuovo push...",
                extra={"slug": context.slug, "branch": default_branch},
            )
            try:
                _run(["git", "pull", "--rebase", "origin", default_branch], cwd=tmp_dir, env=env)
                _attempt_push()
            except subprocess.CalledProcessError as e2:
                raw = (
                    "Push fallito dopo retry con rebase. "
                    "Possibili conflitti tra contenuto locale e remoto. "
                    "Suggerimenti: usare un branch dedicato (GIT_DEFAULT_BRANCH) e aprire una PR, "
                    "oppure — consapevolmente — abilitare il force in orchestratore."
                )
                safe = redact_secrets(raw) if redact_logs else raw
                raise PipelineError(safe, slug=context.slug) from e2

        logger.info(
            "✅ Push completato su %s (%s)",
            repo.full_name,
            default_branch,
            extra={"slug": context.slug, "repo": repo.full_name, "branch": default_branch},
        )
    except subprocess.CalledProcessError as e:
        raw = f"Errore durante le operazioni Git: {e}"
        safe = redact_secrets(raw) if redact_logs else raw
        raise PipelineError(safe, slug=context.slug)
    finally:
        # Cleanup working dir temporanea
        try:
            if tmp_dir.exists() and is_safe_subpath(tmp_dir, base_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            # Non bloccare l'esecuzione in caso di errore di cleanup
            pass
