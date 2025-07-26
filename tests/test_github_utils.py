# tests/test_github_utils.py

import sys
from pathlib import Path
import os
import subprocess

# Patch per trovare src/pipeline sempre, da qualsiasi posizione
project_root = Path(__file__).parent.parent.resolve()
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from pipeline.settings import get_settings
from pipeline.github_utils import push_output_to_github
from github import Github
from github.GithubException import GithubException

def scan_for_dotgit(base_path):
    base_path = Path(base_path)
    found = []
    for p in base_path.rglob('.git'):
        found.append(str(p))
    return found

def list_files(base_path):
    base_path = Path(base_path)
    print(f"\nContenuto di {base_path}:")
    for p in base_path.rglob('*'):
        print("   ", p.relative_to(base_path), "(dir)" if p.is_dir() else "")

def delete_repo_on_github(repo_name, github_token):
    """
    Prova prima a cancellare la repo via API.
    Se fallisce per permessi, prova via GitHub CLI.
    """
    try:
        github = Github(github_token)
        user = github.get_user()
        repo = user.get_repo(repo_name)
        repo.delete()
        print(f"🗑️ Repository '{repo_name}' eliminata con successo su GitHub (via API).")
        return
    except GithubException as e:
        if e.status == 403 or e.status == 401:
            print("⚠️ Permessi insufficienti via API (403/401). Tenterò via GitHub CLI.")
        else:
            print(f"⚠️ Errore API PyGithub: {e}")
            return
    except Exception as e:
        print(f"⚠️ Errore API PyGithub: {e}")

    # Tenta via CLI
    try:
        print(f"Tento eliminazione repo '{repo_name}' via GitHub CLI...")
        subprocess.run(["gh", "repo", "delete", repo_name, "--yes"], check=True)
        print(f"🗑️ Repository '{repo_name}' eliminata via CLI (gh).")
    except Exception as e:
        print(f"❌ Impossibile cancellare la repo '{repo_name}' con nessun metodo. Errore: {e}")

def main():
    settings = get_settings()
    github_token = settings.github_token
    repo_name = "timmy-kb-dummytest"
    # Assumi che il dummy repo sia in filetest/dummy_repo, oppure cambia path in base alla tua struttura attuale
    output_path = str(Path("filetest/dummy_repo").resolve())

    config = {
        "github_token": github_token,
        "github_repo": repo_name,
        "output_path": output_path
    }

    print("📦 TEST: Push su GitHub della repo dummy (filetest/dummy_repo)")
    print(f"Repo: {config['github_repo']}")
    print(f"Path locale: {config['output_path']}")

    list_files(config['output_path'])
    dotgits = scan_for_dotgit(config['output_path'])
    if dotgits:
        print("\n⚠️ ATTENZIONE: Trovate cartelle/file .git nella repo da pushare!")
        for path in dotgits:
            print("    👉", path)
        print("❌ Interrompo il test: elimina tutte le .git dalla dummy_repo prima di riprovare.")
        return
    else:
        print("✅ Nessuna .git trovata nella repo da pushare.")

    try:
        push_output_to_github(config)
        print(f"\n✅ Push completato.")
    except Exception as e:
        print(f"❌ Errore nel test push: {e}")

    # Cleanup finale: cancella la repo su richiesta
    if github_token:
        delete_github = input("\nVuoi cancellare la repo su GitHub? [y/N] ").strip().lower()
        if delete_github == "y":
            delete_repo_on_github(config["github_repo"], github_token)
        else:
            print("La repo rimane su GitHub.")
    else:
        print("⚠️ GITHUB_TOKEN non trovato, impossibile cancellare la repo automaticamente.")

if __name__ == "__main__":
    main()
