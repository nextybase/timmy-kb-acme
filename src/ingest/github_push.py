import subprocess
import logging
import os
import sys
from utils.github_utils import (
    check_gh_cli_installed,
    check_gh_authenticated,
    repo_exists
)

logger = logging.getLogger(__name__)

def ask_push(config: dict) -> bool:
    risposta = input("❓ Vuoi procedere con il push su GitHub? [y/N] ").strip().lower()
    return risposta == "y"

def do_push(config: dict):
    check_gh_cli_installed()
    check_gh_authenticated()

    repo_name = config["repo_name"]
    github_repo = config["github_repo"]
    repo_path = config["md_output_path"]
    visibility = config.get("repo_visibility", "private")

    logger.info(f"🚀 Inizio deploy su GitHub: {github_repo} ({visibility})")

    os.chdir(repo_path)

    if not os.path.exists(".git"):
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "checkout", "-b", "main"], check=True)

    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)

    if repo_exists(config["github_owner"], repo_name):
        logger.warning(f"⚠️  La repository '{github_repo}' esiste già.")
        scelta = input("🔁 Vuoi fare push sulla repo esistente? [y/N] ").strip().lower()
        if scelta == "y":
            subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{github_repo}.git"], check=False)
            subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
            logger.info(f"✅ Push completato su repo esistente: {github_repo}")
        else:
            logger.info("⛔ Push annullato dall’utente.")
    else:
        try:
            subprocess.run([
                "gh", "repo", "create", github_repo,
                f"--{visibility}", "--source=.", "--push"
            ], check=True)
            logger.info(f"✅ Repository '{github_repo}' creata e pushata con successo.")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Errore durante la creazione della repo: {e}")
            sys.exit(1)
