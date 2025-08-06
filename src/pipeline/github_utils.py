"""
github_utils.py

Utility per il deploy automatico della cartella markdown su GitHub.  
Gestisce creazione repository, push forzato su master, gestione repo temporanea e cleanup.  
Supporta override slug/config ed esclude cartelle non desiderate dal deploy (config, raw, ecc).
"""

import shutil
from pathlib import Path
from git import Repo
from github import Github
from github.GithubException import UnknownObjectException

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PushError
from pipeline.config_utils import get_config

logger = get_structured_logger("pipeline.github_utils", "logs/onboarding.log")

def push_output_to_github(md_dir_path: Path, config, slug: str = None) -> str:
    """
    Esegue il deploy automatico della cartella md_dir_path su GitHub.
    Crea la repository se non esiste e forza il push su master.

    Args:
        md_dir_path (Path): Directory contenente i markdown da pushare.
        config: Oggetto configurazione contenente secrets e info GitHub.
        slug (str, opzionale): Identificatore cliente per override config.

    Returns:
        str: Path della directory pubblicata.

    Raises:
        PushError: Se mancano token o repo o se il push fallisce.
    """
    if slug:
        settings = get_config(slug)
        github_token = getattr(settings.secrets, "GITHUB_TOKEN", None)
        repo_name = getattr(settings, "github_repo", None) or f"timmy-kb-{slug}"
        output_path = settings.md_output_path_path
    else:
        github_token = getattr(config.secrets, "GITHUB_TOKEN", None)
        repo_name = getattr(config, "github_repo", None) or f"timmy-kb-{config.slug}"
        output_path = config.md_output_path_path

    if not github_token:
        logger.error("❌ GITHUB_TOKEN mancante: inseriscilo nel file .env o settings.")
        raise PushError("GITHUB_TOKEN mancante!")
    if not repo_name:
        logger.error("❌ github_repo mancante nel config.")
        raise PushError("github_repo mancante nel config!")
    if not output_path.exists():
        logger.error(f"❌ output_path non trovato: {output_path}")
        raise PushError(f"output_path non trovato: {output_path}")

    try:
        github = Github(github_token)
        github_user = github.get_user()
        logger.info(f"🔗 Deploy GitHub per: {github_user.login}/{repo_name} (private)")

        try:
            repo = github_user.get_repo(repo_name)
            logger.info(f"🌱 Repo trovata: {repo_name}")
        except UnknownObjectException:
            logger.info(f"🌱 Repo non trovata, la creo: {repo_name}")
            repo = github_user.create_repo(
                name=repo_name,
                private=True,
                auto_init=False,
                description="Repository generato automaticamente da NeXT"
            )

        temp_dir = Path("tmp_repo_push")
        # Cleanup preventivo della cartella temporanea se esiste
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"🧹 Cartella temporanea '{temp_dir}' rimossa prima del push.")
            except Exception as e:
                logger.warning(f"⚠️ Impossibile rimuovere '{temp_dir}' prima del push: {e}")

        # Copia solo i file utili (.md, immagini, asset dichiarati)
        temp_dir.mkdir(parents=True, exist_ok=True)
        whitelist_ext = {'.md'}
        whitelist_names = {'README.md', 'SUMMARY.md'}

        # Copia i file .md dalla root di output_path
        for file in output_path.glob("*.md"):
            shutil.copy(file, temp_dir / file.name)

        # Se hai asset da includere, aggiungi qui la logica (ad esempio immagini):
        # for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg"]:
        #     for img_file in output_path.glob(f"*{ext}"):
        #         shutil.copy(img_file, temp_dir / img_file.name)

        repo_local = Repo.init(temp_dir)
        files_to_add = [str(p.relative_to(temp_dir)) for p in temp_dir.iterdir() if p.is_file()]
        repo_local.index.add(files_to_add)
        repo_local.index.commit("Upload automatico dei soli file markdown utili da pipeline NeXT")

        remote_url = repo.clone_url.replace("https://", f"https://{github_token}@")
        if "origin" not in [r.name for r in repo_local.remotes]:
            repo_local.create_remote("origin", remote_url)
        else:
            repo_local.remotes.origin.set_url(remote_url)

        repo_local.git.push("origin", "master", force=True)
        logger.info("🚀 Push su GitHub completato.")

        # Cleanup della cartella temporanea anche dopo il push
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"🧹 Cartella temporanea '{temp_dir}' rimossa dopo il push.")
        except Exception as e:
            logger.warning(f"⚠️ Impossibile rimuovere '{temp_dir}' dopo il push: {e}")

        return str(output_path)

    except Exception as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
        raise PushError(f"Errore durante il push su GitHub: {e}")
