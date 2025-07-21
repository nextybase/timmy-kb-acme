# src/pipeline/gitbook_preview.py

import subprocess
import os
from pathlib import Path
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.gitbook_preview", "logs/onboarding.log")

def run_gitbook_docker_preview(config: dict) -> bool:
    """
    Lancia anteprima GitBook in locale tramite Docker (Honkit build + serve).
    Restituisce True se il ciclo build/preview è stato completato, False su errore.
    """
    output_dir = Path(config["md_output_path"]).resolve()
    logger.info(f"📁 Directory corrente per anteprima: {output_dir}")

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
        return False

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
        return True
    except subprocess.CalledProcessError:
        logger.error("❌ Errore durante `honkit serve`.")
        return False
