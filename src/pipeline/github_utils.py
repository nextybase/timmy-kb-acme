# src/pipeline/github_utils.py

import os
import shutil
import subprocess
import sys
from pathlib import Path
from git import Repo
from github import Github
from github.GithubException import UnknownObjectException
from dotenv import load_dotenv
from pipeline.logging_utils import get_structured_logger

load_dotenv()
logger = get_structured_logger("pipeline.github_utils", "logs/onboarding.log")

def check_github_cli_installed():
    """
    Verifica se la GitHub CLI (gh) è installata nel sistema.
    Termina l'esecuzione se non è presente.
    """
    if shutil.which("gh") is None:
        logger.error("❌ GitHub CLI (gh) non trovato. Installa da https://cli.github.com/")
        sys.exit(1)

def check_github_cli_authenticated():
    """
    Verifica che la GitHub CLI sia autenticata (gh auth status).
    Termina l'esecuzione se non autenticata.
    """
    try:
        subprocess.run(["gh", "auth", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        logger.error("❌ GitHub CLI non autenticata. Esegui: gh auth login")
        sys.exit(1)

def check_github_repo_exists(owner: str, name: str) -> bool:
    """
    Verifica se la repository GitHub esiste già (via CLI gh).
    Restituisce True se esiste, False altrimenti.
    """
    try:
        result = subprocess.run(
            ["gh", "repo", "view", f"{owner}/{name}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"⚠️  Errore durante il controllo repo esistente: {e}")
        return False

def push_output_to_github(config: dict) -> bool:
    """
    Esegue il deploy automatico della cartella `output_path`
    su GitHub come repository privata.
    Esclude dal push le cartelle: .git, _book, config, raw
    Restituisce True se il push va a buon fine, False in caso di errore.
    """
    github_token = config.get("github_token") or os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("❌ GITHUB_TOKEN non trovato. Inserisci il token nel file .env o in config.")
        raise RuntimeError("GITHUB_TOKEN mancante!")

    repo_name = config["github_repo"]
    local_path = Path(config["output_path"]).resolve()

    github = Github(github_token)
    github_user = github.get_user()

    logger.info(f"🚀 Inizio deploy su GitHub: {github_user.login}/{repo_name} (private)")

    try:
        repo = github_user.get_repo(repo_name)
        logger.info(f"📦 Repository '{repo_name}' trovata. Eseguo push...")
    except UnknownObjectException:
        logger.info(f"📦 Creo la repository '{repo_name}' su GitHub...")
        repo = github_user.create_repo(
            name=repo_name,
            private=True,
            auto_init=False,  # Repo vuota!
            description="Repository generata automaticamente da NeXT"
        )

    try:
        # Creazione cartella temporanea isolata
        temp_dir = Path("tmp_repo_push")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        shutil.copytree(local_path, temp_dir)

        # Rimuovi eventuale .git dalla sorgente (paranoia mode)
        git_dir = temp_dir / ".git"
        if git_dir.exists() and git_dir.is_dir():
            shutil.rmtree(git_dir)

        # Blacklist delle cartelle da escludere dal push
        EXCLUDE_DIRS = {'.git', '_book', 'config', 'raw'}

        # Inizializza repo Git (di default su master)
        repo_local = Repo.init(temp_dir)
        repo_local.index.add([
            str(p.relative_to(temp_dir))
            for p in temp_dir.rglob("*")
            if (
                not p.is_dir()
                and all(excl not in p.parts for excl in EXCLUDE_DIRS)
            )
        ])
        repo_local.index.commit("📦 Upload automatico da pipeline NeXT")

        # Crea branch main da master e spostati su main
        if 'main' not in repo_local.heads:
            main_branch = repo_local.create_head('main')
        else:
            main_branch = repo_local.heads['main']
        repo_local.head.reference = main_branch
        repo_local.head.reset(index=True, working_tree=True)

        # Push remoto su main (forzato)
        remote_url = repo.clone_url.replace("https://", f"https://{github_token}@")
        if "origin" not in repo_local.remotes:
            repo_local.create_remote("origin", remote_url)
        repo_local.git.push("--set-upstream", "origin", "main", "--force")

        logger.info("✅ Deploy completato con successo.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return True

    except Exception as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
        return False
