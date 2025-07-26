import subprocess
import json
from pathlib import Path
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PreviewError

logger = get_structured_logger("pipeline.gitbook_preview", "logs/onboarding.log")

def ensure_book_json(book_dir):
    book_json_path = Path(book_dir) / "book.json"
    if not book_json_path.exists():
        data = {
            "title": "Timmy KB",
            "author": "Pipeline",
            "plugins": []
        }
        book_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"✅ book.json generato automaticamente in: {book_json_path}")
    else:
        logger.info(f"✅ book.json già presente in: {book_json_path}")

def ensure_package_json(book_dir):
    package_json_path = Path(book_dir) / "package.json"
    if not package_json_path.exists():
        data = {
            "name": "timmy-kb",
            "version": "1.0.0",
            "description": "Dummy package.json auto-generated for Honkit preview",
            "main": "README.md",
            "license": "MIT"
        }
        package_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"✅ package.json generato automaticamente in: {package_json_path}")
    else:
        logger.info(f"✅ package.json già presente in: {package_json_path}")

def run_gitbook_docker_preview(config: dict) -> None:
    output_dir = Path(config["md_output_path"]).resolve()
    logger.info(f"📦 Directory corrente per anteprima: {output_dir}")

    # Assicura file essenziali
    ensure_book_json(output_dir)
    ensure_package_json(output_dir)

    # Step 1: Build (opzionale, ma lasciato per completezza)
    logger.info("🏗️  Avvio build statico Honkit (Docker)...")
    build_cmd = [
        "docker", "run", "--rm", "-it",
        "--workdir", "/app",
        "-v", f"{output_dir}:/app",
        "honkit/honkit", "npx", "honkit", "build"
    ]
    try:
        subprocess.run(build_cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("🚨 Errore durante `honkit build`. Anteprima non avviata.")
        raise PreviewError(f"Errore durante `honkit build`: {e}")

    # Step 2: Serve preview live dai markdown
    logger.info("🧑‍💻 Avvio anteprima GitBook in locale con Docker (preview live)...")
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
        logger.info("ℹ️  Anteprima avviata su http://localhost:4000")
        input("🛑 Premi INVIO per chiudere l’anteprima e continuare...")
        logger.info("🔁 Arresto container Docker...")
        subprocess.run(["docker", "stop", container_name])
    except subprocess.CalledProcessError as e:
        logger.error("🚨 Errore durante `honkit serve`.")
        raise PreviewError(f"Errore durante `honkit serve`: {e}")
