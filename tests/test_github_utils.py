# tests/test_github_utils.py

import sys
import os
import subprocess
from pathlib import Path
import pytest

# Fai vedere src/ come package root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from pipeline.config_utils import get_config, UnifiedConfig
from pipeline.github_utils import push_output_to_github
from github import Github
from github.GithubException import GithubException

SLUG = "dummy"
REPO_NAME = "timmy-kb-dummytest"
DUMMY_REPO_PATH = Path("filetest/dummy_repo")

@pytest.fixture(scope="session", autouse=True)
def ensure_dummy_repo():
    """Assicura che la dummy_repo esista e sia pronta per il test."""
    if not DUMMY_REPO_PATH.exists():
        # Puoi aggiungere qui uno script che genera una dummy_repo se vuoi automatizzare la creazione
        raise RuntimeError(f"Dummy repo non trovata in {DUMMY_REPO_PATH}")

def print_debug_github(config):
    print("\n=== DEBUG CONFIG GITHUB ===")
    for k, v in config.items():
        print(f"{k}: {v}")

def scan_for_dotgit(base_path):
    base_path = Path(base_path)
    return [str(p) for p in base_path.rglob('.git')]

def list_files(base_path):
    base_path = Path(base_path)
    print(f"\nContenuto di {base_path}:")
    for p in base_path.rglob('*'):
        print("   ", p.relative_to(base_path), "(dir)" if p.is_dir() else "")

def delete_repo_on_github(repo_name, github_token):
    try:
        github = Github(github_token)
        user = github.get_user()
        repo = user.get_repo(repo_name)
        repo.delete()
        print(f"🗑️ Repository '{repo_name}' eliminata con successo su GitHub (via API).")
    except GithubException as e:
        if e.status == 403 or e.status == 401:
            print("⚠️ Permessi insufficienti via API (403/401). Tenterò via GitHub CLI.")
        else:
            print(f"⚠️ Errore API PyGithub: {e}")
            return
    except Exception as e:
        print(f"⚠️ Errore API PyGithub: {e}")
        return
    # Tenta via CLI
    try:
        print(f"Tento eliminazione repo '{repo_name}' via GitHub CLI...")
        subprocess.run(["gh", "repo", "delete", repo_name, "--yes"], check=True)
        print(f"🗑️ Repository '{repo_name}' eliminata via CLI (gh).")
    except Exception as e:
        print(f"❌ Impossibile cancellare la repo '{repo_name}' con nessun metodo. Errore: {e}")

def test_github_push_and_cleanup(monkeypatch):
    """
    Test completo del push su GitHub di una repo dummy.
    - Verifica che non siano presenti .git residue.
    - Esegue push.
    - Facoltativamente esegue cleanup finale cancellando la repo.
    """
    unified = get_config(SLUG)
    github_token = unified.secrets.GITHUB_TOKEN
    output_path = str(DUMMY_REPO_PATH.resolve())

    config = {
        "github_token": github_token,
        "github_repo": REPO_NAME,
        "output_path": output_path
    }

    print_debug_github(config)
    list_files(config['output_path'])
    dotgits = scan_for_dotgit(config['output_path'])

    assert not dotgits, f"Trovate cartelle/file .git nella repo da pushare: {dotgits}"

    try:
        push_output_to_github(config)
        print(f"\n✅ Push completato.")
    except Exception as e:
        pytest.fail(f"❌ Errore nel test push: {e}")

    # Cleanup finale (richiesto interattivamente solo in run manuale)
    # Qui si può mettere una variabile d'ambiente per forzare o saltare cleanup
    if github_token and os.environ.get("DELETE_TEST_REPO", "0") == "1":
        delete_repo_on_github(config["github_repo"], github_token)
        print("🧹 Cleanup completato (repo eliminata su GitHub).")
    else:
        print("ℹ️ Cleanup automatico non eseguito. Imposta DELETE_TEST_REPO=1 per eliminare la repo test.")

