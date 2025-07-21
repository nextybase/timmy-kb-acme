from github import Github
from github.GithubException import UnknownObjectException
from utils.logger_utils import get_logger
from pathlib import Path
import shutil
import os
from git import Repo
from dotenv import load_dotenv

load_dotenv()

logger = get_logger("github_push", "logs/onboarding.log")

def do_push(config: dict):
    """
    Esegue il deploy automatico della cartella `output_path`
    su GitHub come repository privata.
    Esclude dal push le cartelle: .git, _book, config, raw
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
        # Aggiungi TUTTI i file tranne quelli nelle EXCLUDE_DIRS
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

        # Pulizia della cartella temporanea
        shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
