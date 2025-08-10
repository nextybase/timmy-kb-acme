"""
github_utils.py

Utility per il deploy automatico della cartella markdown su GitHub.
Gestisce creazione repository, push forzato su master, gestione repo temporanea e cleanup.
Supporta config centralizzata e parametri da settings.

Refactoring:
- Uso di _validate_path_in_base_dir da config_utils
- Eliminata dipendenza da pipeline.utils
- Log uniformati
"""

import os
import shutil
from pathlib import Path
from git import Repo
from github import Github
from github.GithubException import UnknownObjectException

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PushError, PipelineError
from pipeline.config_utils import _validate_path_in_base_dir, get_settings_for_slug
from pipeline.constants import OUTPUT_DIR_NAME, LOGS_DIR_NAME

logger = get_structured_logger("pipeline.github_utils", f"{LOGS_DIR_NAME}/onboarding.log")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings valida.
    """
    if settings:
        return settings
    return get_settings_for_slug()


def push_output_to_github(settings=None, md_dir_path: Path = None) -> str:
    """
    Esegue il deploy automatico della cartella markdown su GitHub.
    Crea il repository se non esiste e forza il push su master.

    Args:
        settings: Settings inizializzati per lo slug corrente.
        md_dir_path: Path contenente i markdown da pushare (default: settings.md_output_path).

    Returns:
        str: Percorso della directory pubblicata.

    Raises:
        PushError: Se mancano token, repo o il push fallisce.
    """
    settings = _resolve_settings(settings)

    github_token = getattr(settings, "GITHUB_TOKEN", None) or os.getenv("GITHUB_TOKEN")
    repo_name = getattr(settings, "GITHUB_REPO", None) or f"timmy-kb-{settings.slug}"
    output_path = md_dir_path or settings.md_output_path

    if not github_token:
        logger.error("❌ GITHUB_TOKEN mancante.")
        raise PushError("GITHUB_TOKEN mancante.")
    if not repo_name:
        logger.error("❌ Nome repository GitHub mancante.")
        raise PushError("Nome repository GitHub mancante.")
    if not output_path.exists():
        logger.error(f"❌ output_path non trovato: {output_path}")
        raise PushError(f"output_path non trovato: {output_path}")

    _validate_path_in_base_dir(output_path, settings.base_dir)

    try:
        github = Github(github_token)
        github_user = github.get_user()
        logger.info(f"👤 Deploy GitHub per utente {github_user.login} → repo: {repo_name} (privata)")

        try:
            repo = github_user.get_repo(repo_name)
            logger.info(f"📂 Repo trovata: {repo_name}")
        except UnknownObjectException:
            logger.info(f"📂 Repo non trovata, creazione in corso: {repo_name}")
            repo = github_user.create_repo(
                name=repo_name,
                private=True,
                auto_init=False,
                description="Repository generato automaticamente da Timmy-KB"
            )

        temp_dir = Path("tmp_repo_push")
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"🗑️ Rimossa cartella temporanea '{temp_dir}' prima del push.")
            except Exception as e:
                logger.warning(f"⚠️ Impossibile rimuovere '{temp_dir}' prima del push: {e}")

        temp_dir.mkdir(parents=True, exist_ok=True)
        for file in output_path.glob("*.md"):
            shutil.copy(file, temp_dir / file.name)

        repo_local = Repo.init(temp_dir)
        repo_local.index.add([str(p.relative_to(temp_dir)) for p in temp_dir.iterdir() if p.is_file()])
        repo_local.index.commit("Upload automatico dei file markdown da pipeline Timmy-KB")

        remote_url = repo.clone_url.replace("https://", f"https://{github_token}@")
        if "origin" not in [r.name for r in repo_local.remotes]:
            repo_local.create_remote("origin", remote_url)
        else:
            repo_local.remotes.origin.set_url(remote_url)

        repo_local.git.push("origin", "master", force=True)
        logger.info("✅ Push su GitHub completato.")

        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"🗑️ Rimossa cartella temporanea '{temp_dir}' dopo il push.")
        except Exception as e:
            logger.warning(f"⚠️ Impossibile rimuovere '{temp_dir}' dopo il push: {e}")

        return str(output_path)

    except Exception as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
        raise PushError(f"Errore durante il push su GitHub: {e}")
