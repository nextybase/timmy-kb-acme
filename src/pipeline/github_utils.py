# src/pipeline/github_utils.py

import os
import shutil
from pathlib import Path
from git import Repo
from github import Github
from github.GithubException import UnknownObjectException

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PushError
from pipeline.constants import LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath  # ✅ nuovo import

logger = get_structured_logger("pipeline.github_utils", f"{LOGS_DIR_NAME}/onboarding.log")


def push_output_to_github(context: ClientContext, md_dir_path: Path = None) -> str:
    """
    Esegue il deploy automatico della cartella markdown su GitHub.
    Crea il repository se non esiste e forza il push su main/master.

    Args:
        context: ClientContext inizializzato per il cliente corrente.
        md_dir_path: Path contenente i markdown da pushare (default: context.md_dir).

    Returns:
        str: Percorso della directory pubblicata.

    Raises:
        PushError: Se mancano token, repo o il push fallisce.
    """
    if not context:
        raise PushError("Context mancante per push_output_to_github")

    github_token = context.settings.get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    repo_name = context.settings.get("GITHUB_REPO") or f"timmy-kb-{context.slug}"
    output_path = md_dir_path or context.md_dir

    if not github_token:
        logger.error("❌ GITHUB_TOKEN mancante.")
        raise PushError("GITHUB_TOKEN mancante.")
    if not repo_name:
        logger.error("❌ Nome repository GitHub mancante.")
        raise PushError("Nome repository GitHub mancante.")
    if not output_path.exists():
        logger.error(f"❌ output_path non trovato: {output_path}")
        raise PushError(f"output_path non trovato: {output_path}")

    # ✅ Controllo path sicuro
    if not is_safe_subpath(output_path, context.base_dir):
        raise PushError(f"Path non sicuro per push: {output_path}")

    # Lista file markdown
    md_files = list(output_path.glob("*.md"))
    if not md_files:
        logger.warning(f"⚠️ Nessun file markdown trovato in {output_path}. Push annullato.")
        return str(output_path)

    logger.info(f"📄 File markdown trovati per il push: {[f.name for f in md_files]}")

    try:
        github = Github(github_token)
        github_user = github.get_user()
        logger.info(f"👤 Deploy GitHub per utente {github_user.login} → repo: {repo_name} (privata)")

        # Controlla se repo esiste, altrimenti la crea
        try:
            repo = github_user.get_repo(repo_name)
            logger.info(f"📂 Repo trovata: {repo_name}")
        except UnknownObjectException:
            logger.info(f"📁 Repo non trovata, creazione in corso: {repo_name}")
            repo = github_user.create_repo(
                name=repo_name,
                private=True,
                auto_init=False,
                description="Repository generata automaticamente da Timmy-KB"
            )

        # Prepara cartella temporanea per push
        temp_dir = Path("tmp_repo_push")
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Copia file markdown nella temp dir
        for file in md_files:
            shutil.copy(file, temp_dir / file.name)

        # Inizializza repo locale
        repo_local = Repo.init(temp_dir)
        repo_local.index.add([str(p.relative_to(temp_dir)) for p in temp_dir.iterdir() if p.is_file()])
        repo_local.index.commit("Upload automatico dei file markdown da pipeline Timmy-KB")

        # Determina branch di default
        default_branch = "main"
        try:
            if repo.default_branch:
                default_branch = repo.default_branch
        except Exception:
            pass

        # Configura remote e push
        remote_url = repo.clone_url.replace("https://", f"https://{github_token}@")
        if "origin" not in [r.name for r in repo_local.remotes]:
            repo_local.create_remote("origin", remote_url)
        else:
            repo_local.remotes.origin.set_url(remote_url)

        logger.info(f"🔄 Push dei file su branch '{default_branch}'...")
        repo_local.git.push("origin", f"HEAD:{default_branch}", force=True)
        logger.info("✅ Push su GitHub completato.")

        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"🗑️ Rimossa cartella temporanea '{temp_dir}' dopo il push.")

        return str(output_path)

    except Exception as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
        raise PushError(f"Errore durante il push su GitHub: {e}")
