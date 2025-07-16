import subprocess
import os
from pathlib import Path
from dotenv import load_dotenv
import logging
import shutil

# Load environment
load_dotenv()
GITHUB_ORG = os.getenv("GITHUB_ORG", "nextybase")
TEMPLATE_REPO = f"{GITHUB_ORG}/timmy-kb-template"
REPO_CLONE_BASE = Path(os.getenv("REPO_CLONE_BASE", ".")).resolve()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

def push_to_github(md_output_path: Path, repo_url: str, branch: str = "main"):
    repo_name = repo_url.split("/")[-1]
    repo_clone_path = REPO_CLONE_BASE / repo_name
    full_repo_url = f"https://github.com/{repo_url}.git"

    logger.info(f"🚀 Inizio push su GitHub → repo: {repo_url}, branch: {branch}")

    try:
        # Verifica se il repo esiste
        result = subprocess.run(["gh", "repo", "view", repo_url],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            logger.info(f"📁 Repo '{repo_url}' non trovata. Creo nuova da template...")
            subprocess.run([
                "gh", "repo", "create", repo_url,
                "--private",
                "--template", TEMPLATE_REPO
            ], check=True)

        # Clonazione repository
        if repo_clone_path.exists():
            shutil.rmtree(repo_clone_path)
        subprocess.run(["git", "clone", full_repo_url], cwd=REPO_CLONE_BASE, check=True)

        # Copia i file Markdown
        for item in Path(md_output_path).iterdir():
            target = repo_clone_path / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy(item, target)

        # Commit e push
        subprocess.run(["git", "add", "."], cwd=repo_clone_path, check=True)
        subprocess.run(["git", "commit", "-m", "🤖 Deploy automatico contenuti KB"], cwd=repo_clone_path, check=True)
        subprocess.run(["git", "push", "origin", branch], cwd=repo_clone_path, check=True)

        logger.info("✅ Push completato con successo.")

    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Errore durante il push: {e}")
