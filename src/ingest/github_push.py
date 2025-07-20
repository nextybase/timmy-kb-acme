from github import Github
from github.GithubException import GithubException, UnknownObjectException
from utils.logger_utils import get_logger
from pathlib import Path
import shutil
import os
from git import Repo

logger = get_logger("github_push", "logs/onboarding.log")

def do_push(config: dict):
    """
    Esegue il deploy automatico della cartella `output_path`
    su GitHub come repository privata.
    """
    github_token = config.get("github_token") or os.getenv("GITHUB_TOKEN")
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
            auto_init=True,
            description="Repository generata automaticamente da NeXT"
        )

    try:
        # Creazione cartella temporanea isolata
        temp_dir = Path("tmp_repo_push")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        shutil.copytree(local_path, temp_dir)

        # Inizializza repo Git
        repo_local = Repo.init(temp_dir)
        repo_local.index.add([str(p.relative_to(temp_dir)) for p in temp_dir.rglob("*") if not p.is_dir()])
        repo_local.index.commit("📦 Upload automatico da pipeline NeXT")

        # Push remoto
        remote_url = repo.clone_url.replace("https://", f"https://{github_token}@")
        if "origin" not in repo_local.remotes:
            repo_local.create_remote("origin", remote_url)
        repo_local.remotes.origin.push(refspec="master:main")

        logger.info("✅ Deploy completato con successo.")
    except Exception as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
