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
    Esegue il deploy automatico della cartella `output_path`
    su GitHub come repository privata.
    Esclude dal push le cartelle: .git, _book, config, raw (in qualunque livello, anche annidato).
    Solleva PushError se il push fallisce.
    Restituisce il percorso della temp_dir usata per il push (utile per cleanup successivi).
    """
    settings = get_settings()
    github_token = config.get("github_token") or getattr(settings, "github_token", None)
    if not github_token:
        logger.error("❌ GITHUB_TOKEN non trovato. Inserisci il token nel file .env, settings o in config.")
        raise PushError("GITHUB_TOKEN mancante!")

    repo_name = config["github_repo"]
    local_path = Path(config["output_path"]).resolve()

    try:
        github = Github(github_token)
        github_user = github.get_user()
        logger.info(f"🚀 Inizio deploy su GitHub: {github_user.login}/{repo_name} (private)")

        try:
            repo = github_user.get_repo(repo_name)
            logger.info(f"📦 Repository '{repo_name}' trovata. Eseguo push...")
        except UnknownObjectException:
            logger.info(f"📦 Creo la repository '{repo_name}' su GitHub...")
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

        git_dir = temp_dir / ".git"
        if git_dir.exists() and git_dir.is_dir():
            shutil.rmtree(git_dir)

        EXCLUDE_DIRS = {'.git', '_book', 'config', 'raw'}

        repo_local = Repo.init(temp_dir)
        repo_local.index.add([
            str(p.relative_to(temp_dir))
            for p in temp_dir.rglob("*")
            if (
                not p.is_dir()
                and all(excl not in p.parts for excl in EXCLUDE_DIRS)
            )
        ])
        repo_local.index.commit("📦 Upload automatico da pipeline NeXT")

        if 'main' not in repo_local.heads:
            main_branch = repo_local.create_head('main')
        else:
            main_branch = repo_local.heads['main']
        repo_local.head.reference = main_branch
        repo_local.head.reset(index=True, working_tree=True)

        remote_url = repo.clone_url.replace("https://", f"https://{github_token}@")
        if "origin" not in repo_local.remotes:
            repo_local.create_remote("origin", remote_url)
        repo_local.git.push("--set-upstream", "origin", "main", "--force")

        logger.info("✅ Deploy completato con successo.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return str(temp_dir)

    except Exception as e:
        logger.error(f"❌ Errore durante il push su GitHub: {e}")
        raise PushError(f"Errore durante il push su GitHub: {e}")
