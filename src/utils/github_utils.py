import subprocess
import shutil
import logging
import sys

logger = logging.getLogger(__name__)

def check_gh_cli_installed():
    if shutil.which("gh") is None:
        logger.error("❌ GitHub CLI (gh) non trovato. Installa da https://cli.github.com/")
        sys.exit(1)

def check_gh_authenticated():
    try:
        subprocess.run(["gh", "auth", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        logger.error("❌ GitHub CLI non autenticata. Esegui: gh auth login")
        sys.exit(1)

def repo_exists(owner: str, name: str) -> bool:
    """
    Verifica se la repository GitHub esiste già per evitare duplicati.
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
