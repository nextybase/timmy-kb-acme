import shutil
from pathlib import Path
from git import Repo
from github import Github
from github.GithubException import UnknownObjectException
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PushError
from pipeline.settings import get_settings

logger = get_structured_logger("pipeline.github_utils", "logs/onboarding.log")

def push_output_to_github(config: dict) -> str:
    """
    Esegue il deploy automatico della cartella `output_path` su GitHub.
    Esclude .git, _book, config, raw. Crea repo se non esiste.
    Ritorna la temp_dir usata per il push (da pulire manualmente).
    """
    settings = get_settings()
    github_token = (
        config.get("github_token")
        or getattr(settings, "github_token", None)
    )
    if not github_token:
        logger.error("❌ GITHUB_TOKEN mancante: inseriscilo nel file .env o settings.")
        raise PushError("GITHUB_TOKEN mancante!")

    repo_name = config["github_repo"]
    local_path = Path(config["output_path"]).resolve()

    try:
        github = Github(github_token)
        github_user = github.get_user()
        logger.info(f"🚀 Deploy GitHub per: {github_user.login}/{repo_name} (private)")

        try:
            repo = github_user.get_repo(repo_name)
            logger.info(f"📦 Repo trovata: {repo_name}")
        except UnknownObjectException:
            logger.info(f"📦 Repo non trovata, la creo: {repo_name}")
            repo = github_user.create_repo(
                name=repo_name,
                private=True,
                auto_init=False,
                description="Repository generata automaticamente da NeXT"
            )

        temp_dir = Path("tmp_repo_push")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        shutil.copytree(local_path, temp_dir)

        # Pulizia cartelle da escludere
        EXCLUDE_DIRS = {'.git', '_book', 'config', 'raw'}
        for excl in EXCLUDE_DIRS:
            excl_path = temp_dir / excl
            if excl_path.exists():
                shutil.rmtree(excl_path, ignore_errors=True)

        repo_local = Repo.init(temp_dir)
        files_to_add = [
            str(p.relative_to(temp_dir))
            for p in temp_dir.rglob("*")
            if p.is_file() and all(x not in p.parts for x in EXCLUDE_DIRS)
        ]
        repo_local.index.add(files_to_add)
        repo_local.index.commit("📦 Upload automatico da pipeline NeXT")

        main_branch = repo_local.create_head('main') if 'main' not in repo_local.heads else repo_local.heads['main']
        repo_local.head.reference = main_branch
        repo_local.head.reset(index=True, working_tree=True)

        remote_url = repo.clone_url.replace("https://", f"https://{github_token}@")
        if "origin" not in repo_local.remotes:
            repo_local.create_remote("origin", remote_url)
        repo_local.git.push("--set-upstream", "origin", "main", "--force")

        logger.info("✅ Push su GitHub completato.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return str(temp_dir)

    except Exception as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
        raise PushError(f"Errore durante il push su GitHub: {e}")
