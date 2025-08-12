"""
Utility per interagire con GitHub:
- Creazione repo cliente
- Push contenuto cartella 'book' (solo file .md senza .bak)
"""

import shutil
import tempfile
import subprocess
from pathlib import Path

from github import Github
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError
from pipeline.path_utils import is_safe_subpath  # sicurezza path

logger = get_structured_logger("pipeline.github_utils")


def push_output_to_github(context, github_token: str, confirm_push: bool = True) -> None:
    """
    Esegue il push dei file .md presenti nella cartella 'book' del cliente su GitHub.
    Crea il repository se non esiste.

    :param context: ClientContext
    :param github_token: Token personale GitHub
    :param confirm_push: Se True, chiede conferma prima di pushare
    """
    book_dir = context.md_dir
    if not book_dir.exists():
        raise PipelineError(f"Cartella book non trovata: {book_dir}",
                            slug=context.slug, file_path=book_dir)

    # Trova solo file .md validi (no .bak) e in path sicuro
    md_files = [
        f for f in book_dir.glob("*.md")
        if not f.name.endswith(".bak") and is_safe_subpath(f, book_dir)
    ]
    if not md_files:
        logger.warning("⚠️ Nessun file .md valido trovato nella cartella book. Push annullato.",
                       extra={"slug": context.slug})
        return

    logger.info(f"📦 Trovati {len(md_files)} file .md da pushare.",
                extra={"slug": context.slug})

    # Conferma operazione se richiesto
    if confirm_push:
        logger.info("📤 Preparazione push su GitHub", extra={"slug": context.slug})
    else:
        logger.info("Modalità non-interattiva: push GitHub senza conferma", extra={"slug": context.slug})

    # Autenticazione GitHub
    gh = Github(github_token)
    user = gh.get_user()
    repo_name = f"timmy-kb-{context.slug}"

    # Recupera o crea repo remoto
    try:
        repo = user.get_repo(repo_name)
        logger.info(f"🔄 Repository remoto trovato: {repo.full_name}",
                    extra={"slug": context.slug, "repo": repo.full_name})
    except Exception:
        logger.info(f"➕ Repository non trovato. Creazione di {repo_name}...",
                    extra={"slug": context.slug})
        repo = user.create_repo(repo_name, private=True)
        logger.info(f"✅ Repository creato: {repo.full_name}",
                    extra={"slug": context.slug, "repo": repo.full_name})

    # Push locale temporaneo
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Copia i file .md nella cartella temporanea
        for f in md_files:
            shutil.copy2(f, tmp_path / f.name)

        try:
            subprocess.run(["git", "init"], cwd=tmp_path, check=True)
            subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, check=True)
            subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
            commit_msg = f"Aggiornamento contenuto KB per cliente {context.slug}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=tmp_path, check=True)

            remote_url = repo.clone_url.replace(
                "https://", f"https://{github_token}@"
            )
            subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=tmp_path, check=True)
            subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=tmp_path, check=True)

            logger.info(f"✅ Push completato su {repo.full_name}",
                        extra={"slug": context.slug, "repo": repo.full_name})
        except subprocess.CalledProcessError as e:
            raise PipelineError(f"Errore durante il push su GitHub: {e}",
                                slug=context.slug)

