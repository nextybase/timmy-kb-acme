import subprocess
import json
from pathlib import Path
from typing import Union
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PreviewError
from pipeline.config_utils import TimmyConfig

logger = get_structured_logger("pipeline.gitbook_preview", "logs/onboarding.log")

def ensure_book_json(book_dir: Path) -> None:
    """
    Assicura la presenza del file book.json minimale per build/serve Honkit.
    """
    book_json_path = book_dir / "book.json"
    if not book_json_path.exists():
        data = {
            "title": "Timmy KB",
            "author": "Pipeline",
            "plugins": []
        }
        book_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"✅ book.json generato in: {book_json_path}")
    else:
        logger.info(f"📘 book.json già presente: {book_json_path}")

def ensure_package_json(book_dir: Path) -> None:
    """
    Assicura la presenza del file package.json minimale.
    """
    package_json_path = book_dir / "package.json"
    if not package_json_path.exists():
        data = {
            "name": "timmy-kb",
            "version": "1.0.0",
            "description": "Auto-generated for Honkit preview",
            "main": "README.md",
            "license": "MIT"
        }
        package_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"✅ package.json generato in: {package_json_path}")
    else:
        logger.info(f"📦 package.json già presente: {package_json_path}")

def run_gitbook_docker_preview(config: Union[dict, TimmyConfig]) -> None:
    """
    Avvia anteprima GitBook (Honkit) in locale via Docker.
    """
    # Compatibilità: accetta sia config[md_output_path] sia TimmyConfig
    md_output_path = Path(config["md_output_path"] if isinstance(config, dict) else config.md_output_path).resolve()
    logger.info(f"📦 Directory per anteprima: {md_output_path}")

    ensure_book_json(md_output_path)
    ensure_package_json(md_output_path)

    # Step 1: Build statico (opzionale)
    logger.info("🏗️  Build statico Honkit (Docker)...")
    build_cmd = [
        "docker", "run", "--rm", "-it",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npx", "honkit", "build"
    ]
    try:
        subprocess.run(build_cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("🚨 Errore durante `honkit build`.")
        raise PreviewError(f"Errore `honkit build`: {e}")

    # Step 2: Serve preview live
    logger.info("🧑‍💻 Avvio anteprima GitBook (Docker)...")
    container_name = "honkit_preview"
    serve_cmd = [
        "docker", "run", "-d", "--rm",
        "--name", container_name,
        "-p", "4000:4000",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npx", "honkit", "serve"
    ]
    try:
        subprocess.run(serve_cmd, check=True)
        logger.info("ℹ️ Anteprima live avviata: http://localhost:4000")
        input("🛑 Premi INVIO per chiudere l’anteprima...")
        logger.info("🔁 Arresto container Docker...")
        subprocess.run(["docker", "stop", container_name])
    except subprocess.CalledProcessError as e:
        logger.error("🚨 Errore durante `honkit serve`.")
        raise PreviewError(f"Errore `honkit serve`: {e}")
