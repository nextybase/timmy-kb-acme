# src/pipeline/github_utils.py
"""
Utility per interagire con GitHub:
- Creazione/rilevamento repo cliente
- Push del contenuto della cartella 'book' (solo file .md, esclusi .bak)
- Branch di default configurabile via (in ordine di priorità):
    1) context.env["GIT_DEFAULT_BRANCH"]
    2) os.getenv("GIT_DEFAULT_BRANCH")
    3) fallback "main"
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable, Iterable

from github import Github
from github.GithubException import GithubException

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError
from pipeline.path_utils import is_safe_subpath  # sicurezza path


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

    Args:
        context: Oggetto compatibile con `_SupportsContext`.

    Returns:
        Nome del branch da usare come default.
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
    github_token: str,
    confirm_push: bool = True,
) -> None:
    """Esegue il push dei file `.md` presenti nella cartella `book` del cliente su GitHub.

    Se il repository non esiste, viene creato nel namespace dell'utente associato al token.
    I file considerati sono esclusivamente quelli con estensione `.md` (esclusi `.bak`), e
    solo se i relativi path ricadono **sotto** `context.md_dir` (path-safety).

    Args:
        context: Contesto con attributi `slug`, `md_dir` e (opz.) `env`.
        github_token: Token personale GitHub (PAT).
        confirm_push: Se `False`, NON esegue il push (il consenso/prompt è gestito dagli orchestratori).

    Raises:
        PipelineError: Se `book_dir` non esiste, oppure in caso di errori durante il push.
    """
    book_dir = context.md_dir
    if not book_dir.exists():
        raise PipelineError(
            f"Cartella book non trovata: {book_dir}",
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
        logger.warning(
            "⚠️ Nessun file .md valido trovato nella cartella book. Push annullato.",
            extra={"slug": context.slug},
        )
        return

    if confirm_push is False:
        logger.info(
            "Push disattivato: confirm_push=False (dry run a carico dell'orchestratore).",
            extra={"slug": context.slug},
        )
        return

    default_branch = _resolve_default_branch(context)
    logger.info(
        f"📤 Preparazione push su GitHub (branch: {default_branch})",
        extra={"slug": context.slug},
    )

    # Autenticazione GitHub
    gh = Github(github_token)
    user = gh.get_user()
    repo_name = f"timmy-kb-{context.slug}"

    # Recupera o crea repo remoto
    try:
        repo = user.get_repo(repo_name)
        logger.info(
            f"🔄 Repository remoto trovato: {repo.full_name}",
            extra={"slug": context.slug, "repo": repo.full_name},
        )
    except GithubException:
        logger.info(
            f"➕ Repository non trovato. Creazione di {repo_name}...",
            extra={"slug": context.slug},
        )
        repo = user.create_repo(repo_name, private=True)
        logger.info(
            f"✅ Repository creato: {repo.full_name}",
            extra={"slug": context.slug, "repo": repo.full_name},
        )

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

            # Config remota senza esporre il token nell'URL
            remote_url = repo.clone_url  # usa https
            subprocess.run(
                ["git", "remote", "add", "origin", remote_url],
                cwd=tmp_path,
                check=True,
            )

            # Inietta il PAT come header HTTP temporaneo (Basic x-access-token:<PAT>)
            header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
            extra = f"http.https://github.com/.extraheader=Authorization: Basic {header}"

            subprocess.run(
                ["git", "-c", extra, "push", "-u", "origin", default_branch, "--force"],
                cwd=tmp_path,
                check=True,
            )

            logger.info(
                f"✅ Push completato su {repo.full_name} ({default_branch})",
                extra={"slug": context.slug, "repo": repo.full_name},
            )
        except subprocess.CalledProcessError as e:
            raise PipelineError(
                f"Errore durante il push su GitHub: {e}", slug=context.slug
            )
