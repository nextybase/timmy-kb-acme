"""
gitbook_preview.py

Genera e avvia la preview locale della documentazione (GitBook/Honkit)
usando container Docker isolato.

Modifiche Fase 2:
- Validazione path con _validate_path_in_base_dir
- Uso costanti da constants.py
- Eccezioni uniformi (PreviewError)
- Logger coerente con il resto della pipeline
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Union

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PreviewError
from pipeline.config_utils import get_settings_for_slug
from pipeline.constants import BOOK_JSON_NAME, PACKAGE_JSON_NAME
from pipeline.utils import _validate_path_in_base_dir

logger = get_structured_logger("pipeline.gitbook_preview")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings.
    """
    return settings or get_settings_for_slug()


def ensure_book_json(book_dir: Path) -> None:
    """
    Garantisce la presenza di un file book.json di base nella directory markdown.
    """
    _validate_path_in_base_dir(book_dir, book_dir.parent)
    book_json_path = book_dir / BOOK_JSON_NAME

    if not book_json_path.exists():
        data = {
            "title": "Timmy KB",
            "author": "Pipeline",
            "plugins": []
        }
        try:
            book_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"📚 book.json generato in: {book_json_path}")
        except Exception as e:
            raise PreviewError(f"Errore generazione book.json: {e}")
    else:
        logger.info(f"📚 book.json già presente: {book_json_path}")


def ensure_package_json(book_dir: Path) -> None:
    """
    Garantisce la presenza di un file package.json di base nella directory markdown.
    """
    _validate_path_in_base_dir(book_dir, book_dir.parent)
    package_json_path = book_dir / PACKAGE_JSON_NAME

    if not package_json_path.exists():
        data = {
            "name": "timmy-kb",
            "version": "1.0.0",
            "description": "Auto-generated for Honkit preview",
            "main": "README.md",
            "license": "MIT",
            "scripts": {
                "build": "honkit build",
                "serve": "honkit serve"
            }
        }
        try:
            package_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"📦 package.json generato in: {package_json_path}")
        except Exception as e:
            raise PreviewError(f"Errore generazione package.json: {e}")
    else:
        logger.info(f"📦 package.json già presente: {package_json_path}")


def run_gitbook_docker_preview(
    config: Union[dict, None] = None,
    port: int = 4000,
    container_name: str = "honkit_preview",
    settings=None
) -> None:
    """
    Avvia la preview GitBook/Honkit in Docker e garantisce
    la rimozione del container al termine o in caso di errore/interruzione.
    """
    settings = _resolve_settings(settings)
    _validate_path_in_base_dir(settings.md_output_path, settings.base_dir)

    md_output_path = None
    if config is None:
        md_output_path = settings.md_output_path.resolve()
    elif isinstance(config, dict):
        md_output_path = Path(config.get("md_output_path", settings.md_output_path)).resolve()
    else:
        md_output_path = Path(getattr(config, "md_output_path", settings.md_output_path)).resolve()

    logger.info(f"📂 Directory per anteprima: {md_output_path}")

    ensure_book_json(md_output_path)
    ensure_package_json(md_output_path)

    # Build static
    build_cmd = [
        "docker", "run", "--rm",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npm", "run", "build"
    ]
    try:
        subprocess.run(build_cmd, check=True)
        logger.info("🏗️ Build statica Honkit completata.")
    except subprocess.CalledProcessError as e:
        logger.error("❌ Errore durante 'honkit build'.")
        raise PreviewError(f"Errore 'honkit build': {e}")

    # Serve live preview
    serve_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:{port}",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npm", "run", "serve"
    ]
    try:
        proc = subprocess.run(serve_cmd, check=True, capture_output=True, text=True)
        container_id = proc.stdout.strip()
        logger.info(f"🌍 Anteprima disponibile su: http://localhost:{port} (container: {container_id})")

        if not os.environ.get("BATCH_TEST"):
            input("⏸️ Premi INVIO per chiudere l'anteprima e arrestare Docker...")
        logger.info("🛑 Arresto container Docker...")
        subprocess.run(["docker", "stop", container_name], check=False)
        subprocess.run(["docker", "rm", "-f", container_name], check=False)

    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Errore durante 'honkit serve': {e}")
        raise PreviewError(f"Errore 'honkit serve': {e}")
