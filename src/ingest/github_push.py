import subprocess
import logging
import os
import shutil
import sys

logger = logging.getLogger(__name__)

def ask_push(config: dict) -> bool:
    """
    Chiede all’utente se vuole procedere con il push su GitHub.
    """
    risposta = input("❓ Vuoi procedere con il push su GitHub? [y/N] ").strip().lower()
    return risposta == "y"

def check_gh_cli():
    """
    Verifica che il binario 'gh' (GitHub CLI) sia disponibile nel sistema.
    """
    if shutil.which("gh") is None:
        logger.error("❌ GitHub CLI (gh) non trovato. Installa 'gh' da https://cli.github.com/")
        sys.exit(1)

def do_push(config: dict):
    """
    Esegue il push su GitHub del contenuto generato nella pipeline.
    Richiede che il repo sia già inizializzato come Git repo.
    """
    check_gh_cli()

    repo_name = config["repo_name"]
    github_repo = config["github_repo"]
    repo_path = config["md_output_path"]
    visibility = config.get("repo_visibility", "private")  # può essere 'private' o 'public'

    logger.info(f"📦 Inizio creazione repo {github_repo} ({visibility}) e push del contenuto...")

    try:
        os.chdir(repo_path)

        if not os.path.exists(".git"):
            subprocess.run(["git", "init"], check=True)
            subprocess.run(["git", "checkout", "-b", "main"], check=True)

        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)

        subprocess.run([
            "gh", "repo", "create", github_repo,
            f"--{visibility}", "--source=.", "--push"
        ], check=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
        sys.exit(1)
