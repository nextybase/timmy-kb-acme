import shutil
from pathlib import Path
from git import Repo
from github import Github
from github.GithubException import UnknownObjectException
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PushError
from pipeline.config_utils import get_config

logger = get_structured_logger("pipeline.github_utils", "logs/onboarding.log")

def push_output_to_github(config: dict, slug: str = None) -> str:
    """
    Esegue il deploy automatico della cartella `output_path` su GitHub.
    Esclude .git, _book, config, raw. Crea repo se non esiste.
    Ritorna la temp_dir usata per il push (da pulire manualmente).
    - Se slug non è fornito, si assume che config contenga tutto il necessario.
    - Se slug è fornito, i valori mancanti vengono recuperati dal get_config(slug).
    """
    # Recupera config e/o slug da pipeline
    if slug:
        settings = get_config(slug)
        github_token = (
            config.get("github_token") or
            getattr(settings.secrets, "GITHUB_TOKEN", None)
        )
        repo_name = config.get("github_repo") or f"timmy-kb-{slug}"
        output_path = Path(config.get("output_path") or settings.config.md_output_path).resolve()
    else:
        github_token = config.get("github_token")
        repo_name = config.get("github_repo")
        output_path = Path(config["output_path"]).resolve()

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
        logger.info(f"🚀 Deploy GitHub per: {github_user.login}/{repo_name} (private)")

        # Crea o recupera la repo remota
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
        shutil.copytree(output_path, temp_dir)

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
