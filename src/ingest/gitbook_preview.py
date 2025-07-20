import subprocess
import os
from pathlib import Path
from utils.logger_utils import get_logger
logger = get_logger("gitbook_preview", "logs/onboarding.log")


def run_gitbook_preview(config: dict):
    """
    Lancia anteprima GitBook in locale con Docker (build + serve).
    Serve in background, poi aspetta input utente per chiudere il container.
    """
    output_dir = Path(config["md_output_path"]).resolve()
    logger.info(f"📁 Directory corrente: {output_dir}")

    # 1. Build statico
    logger.info("🔧 Avvio build statico Honkit (Docker)...")
    build_cmd = [
        "docker", "run", "--rm", "-it",
        "--workdir", "/app",
        "-v", f"{output_dir}:/app",
        "honkit/honkit", "npx", "honkit", "build"
    ]
    try:
        subprocess.run(build_cmd, check=True)
    except subprocess.CalledProcessError:
        logger.error("❌ Errore durante `honkit build`. Anteprima non avviata.")
        return

    # 2. Serve in modalità detached
    logger.info("🐳 Avvio anteprima GitBook in locale con Docker (in background)...")
    container_name = "honkit_preview"
    serve_cmd = [
        "docker", "run", "-d", "--rm",
        "--name", container_name,
        "-p", "4000:4000",
        "--workdir", "/app",
        "-v", f"{output_dir}:/app",
        "honkit/honkit", "npx", "honkit", "serve"
    ]
    try:
        subprocess.run(serve_cmd, check=True)
        logger.info("✅ Anteprima avviata su http://localhost:4000")
        input("🔁 Premi INVIO per chiudere l’anteprima e continuare...")

        logger.info("🛑 Arresto container Docker...")
        subprocess.run(["docker", "stop", container_name])
    except subprocess.CalledProcessError:
        logger.error("❌ Errore durante `honkit serve`.")
