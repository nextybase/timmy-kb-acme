# src/pipeline/github_utils.py
"""
Utility per interagire con GitHub:
- Creazione/rilevamento repo cliente
- Push del contenuto della cartella 'book' (solo file .md, esclusi .bak)
- Branch di default configurabile via (in ordine di priorità):
    1) context.env["GIT_DEFAULT_BRANCH"]
    2) os.getenv("GIT_DEFAULT_BRANCH")
    3) fallback "main"

Note architetturali (v1.0.3+):
- Nessuna interattività in questo modulo (niente prompt/input). Le decisioni di
  conferma push sono responsabilità degli orchestratori (CLI/UX).

Aggiornamento:
- Introduce la redazione dei segreti nei log/messaggi d'errore come opzione (redact_logs=False di default).
- Migliorati i metadati strutturati nei log (repo/branch) e l’hardening degli errori in creazione repo.
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
from pipeline.env_utils import redact_secrets  # 🔐 redazione

logger = get_structured_logger("pipeline.github_utils")


@runtime_checkable
class _SupportsContext(Protocol):
    """Protocol minimale per il contesto richiesto da queste utility.

    Richiede:
        - slug: str — identificativo cliente, usato per naming e logging.
        - md_dir: Path — directory che contiene i markdown da pubblicare.
        - env: dict — mappa di variabili d'ambiente risolte (opzionale).
    """
    slug: str
    md_dir: Path
    env: dict


def _resolve_default_branch(context: _SupportsContext) -> str:
    """Risoluzione branch di default con fallback a 'main'.

    Ordine di priorità:
      1) `context.env["GIT_DEFAULT_BRANCH"]` o `context.env["GITHUB_BRANCH"]` (se presenti)
      2) variabili di processo: `GIT_DEFAULT_BRANCH` o `GITHUB_BRANCH`
      3) fallback sicuro: `"main"`
    """
    # 1) variabili nel contesto (preferite)
    if getattr(context, "env", None):
        br = context.env.get("GIT_DEFAULT_BRANCH") or context.env.get("GITHUB_BRANCH")
        if br:
            return br

    # 2) variabili d'ambiente
    br = os.getenv("GIT_DEFAULT_BRANCH") or os.getenv("GITHUB_BRANCH")
    if br:
        return br

    # 3) fallback sicuro
    return "main"


def push_output_to_github(
    context: _SupportsContext,
    *,
    github_token: str,
    do_push: bool = True,
    redact_logs: bool = False,  # 👈 flag opzionale (default: nessun cambio di comportamento)
) -> None:
    """Esegue il push dei file `.md` presenti nella cartella `book` del cliente su GitHub.

    Se il repository non esiste, viene creato nel namespace dell'utente associato al token.
    I file considerati sono esclusivamente quelli con estensione `.md` (esclusi `.bak`), e
    solo se i relativi path ricadono **sotto** `context.md_dir` (path-safety).

    Architettura:
        - Nessun prompt/nessuna conferma qui: l'orchestratore decide e passa `do_push`.
        - Nessun `sys.exit()`; in caso di errore solleva `PipelineError`.

    Args:
        context: Contesto con attributi `slug`, `md_dir` e (opz.) `env`.
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

    # ✅ Guard-rail: il book_dir deve essere sotto la base del cliente, se disponibile
    base_dir = getattr(context, "base_dir", None)
    if base_dir and not is_safe_subpath(book_dir, base_dir):
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
    msg = f"📤 Preparazione push su GitHub (branch: {default_branch})"
    logger.info(
        redact_secrets(msg) if redact_logs else msg,
        extra={"slug": context.slug, "branch": default_branch},
    )

    # Autenticazione GitHub
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

    # Push locale temporaneo
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Copia preservando la struttura relativa
        for f in md_files:
            dst = tmp_path / f.relative_to(book_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

        try:
            # init repo locale
            subprocess.run(["git", "init"], cwd=tmp_path, check=True)
            subprocess.run(["git", "checkout", "-b", default_branch], cwd=tmp_path, check=True)
            subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

            commit_msg = f"Aggiornamento contenuto KB per cliente {context.slug}"
            subprocess.run(
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
                cwd=tmp_path,
                check=True,
            )

            # Config remota (https) e push con header via ENV (evita leak nel command line)
            remote_url = repo.clone_url  # https://github.com/<org>/<repo>.git
            subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=tmp_path, check=True)

            header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
            env = os.environ.copy()
            env["GIT_HTTP_EXTRAHEADER"] = f"Authorization: Basic {header}"

            subprocess.run(
                ["git", "push", "-u", "origin", default_branch, "--force"],
                cwd=tmp_path,
                check=True,
                env=env,  # 👈 il token NON appare nel comando in caso di errore
            )

            msg = f"✅ Push completato su {repo.full_name} ({default_branch})"
            logger.info(
                redact_secrets(msg) if redact_logs else msg,
                extra={"slug": context.slug, "repo": repo.full_name, "branch": default_branch},
            )
        except subprocess.CalledProcessError as e:
            # Messaggio sicuro: non include l’header in chiaro/base64 nella command line
            raw = f"Errore durante il push su GitHub: {e}"
            safe = redact_secrets(raw) if redact_logs else raw
            raise PipelineError(safe, slug=context.slug)
