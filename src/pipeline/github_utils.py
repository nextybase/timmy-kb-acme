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

        shutil.copytree(output_path, temp_dir)

        # Esclude directory non desiderate dal push
        EXCLUDE_DIRS = {'.git', '_book', 'config', 'raw'}
        for excl in EXCLUDE_DIRS:
            excl_path = temp_dir / excl
            if excl_path.exists():
                try:
                    shutil.rmtree(excl_path, ignore_errors=True)
                    logger.info(f"🧹 Rimossa sottocartella '{excl}' dalla repo temporanea.")
                except Exception as e:
                    logger.warning(f"⚠️ Impossibile rimuovere '{excl_path}': {e}")

        repo_local = Repo.init(temp_dir)
        files_to_add = [str(p.relative_to(temp_dir)) for p in temp_dir.rglob("*")
                        if p.is_file() and all(x not in p.parts for x in EXCLUDE_DIRS)]
        repo_local.index.add(files_to_add)
        repo_local.index.commit("Upload automatico da pipeline NeXT")

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
