# src/pipeline/github_utils.py
"""
Utility per interagire con GitHub:
- Creazione repo cliente
- Push contenuto cartella 'book' (solo file .md senza .bak)
"""
import shutil
import tempfile
import subprocess
import base64
from pathlib import Path

from github import Github
from github.GithubException import GithubException

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError
from pipeline.path_utils import is_safe_subpath  # sicurezza path

logger = get_structured_logger("pipeline.github_utils")


def push_output_to_github(context, github_token: str, confirm_push: bool = True) -> None:
    """
    Esegue il push dei file .md presenti nella cartella 'book' del cliente su GitHub.
    Crea il repository se non esiste.

    :param context: ClientContext (deve esporre .md_dir e .slug)
    :param github_token: Token personale GitHub (PAT)
    :param confirm_push: Se False, NON esegue il push (il prompt/consenso va gestito dagli orchestratori).
    """
    book_dir = context.md_dir
    if not book_dir.exists():
        raise PipelineError(
            f"Cartella book non trovata: {book_dir}",
            slug=context.slug,
            file_path=book_dir,
        )

    # Trova file .md (anche nelle sottocartelle), escludendo .bak e assicurando path sicuri
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

    logger.info(
        f"📦 Trovati {len(md_files)} file .md da pushare.",
        extra={"slug": context.slug},
    )

    # Rispetta il flag: niente I/O qui, il consenso avviene a livello CLI/orchestratore
    if confirm_push is False:
        logger.info(
            "Push disattivato: confirm_push=False (dry run a carico dell'orchestratore).",
            extra={"slug": context.slug},
        )
        return

    logger.info("📤 Preparazione push su GitHub", extra={"slug": context.slug})

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

        # Copia preservando la struttura di directory relativa
        for f in md_files:
            dst = tmp_path / f.relative_to(book_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

        try:
            subprocess.run(["git", "init"], cwd=tmp_path, check=True)
            subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, check=True)
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
            remote_url = repo.clone_url
            subprocess.run(
                ["git", "remote", "add", "origin", remote_url],
                cwd=tmp_path,
                check=True,
            )

            # Inietta il PAT come header HTTP temporaneo (Basic x-access-token:<PAT>)
            header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
            extra = f"http.https://github.com/.extraheader=Authorization: Basic {header}"

            subprocess.run(
                ["git", "-c", extra, "push", "-u", "origin", "main", "--force"],
                cwd=tmp_path,
                check=True,
            )

            logger.info(
                f"✅ Push completato su {repo.full_name}",
                extra={"slug": context.slug, "repo": repo.full_name},
            )
        except subprocess.CalledProcessError as e:
            raise PipelineError(
                f"Errore durante il push su GitHub: {e}", slug=context.slug
            )
