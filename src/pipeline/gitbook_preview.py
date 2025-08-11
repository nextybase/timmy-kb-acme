# src/pipeline/gitbook_preview.py
"""
Genera e avvia la preview locale della documentazione (GitBook/Honkit)
usando container Docker isolato.

Refactor v1.0:
- Validazione path con is_safe_subpath da path_utils.py
- Uso costante da constants.py
- Eccezioni uniformi (PreviewError)
- Logger coerente con il resto della pipeline
- Rimossi _resolve_settings, uso diretto di ClientContext
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Union

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PreviewError, PipelineError
from pipeline.constants import BOOK_JSON_NAME, PACKAGE_JSON_NAME
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath  # ✅ nuovo import per robustezza path

logger = get_structured_logger("pipeline.gitbook_preview")


def ensure_book_json(book_dir: Path) -> None:
    """
    Garantisce la presenza di un file book.json nella directory markdown.
    """
    if not is_safe_subpath(book_dir, book_dir.parent):  # ✅ controllo path sicuro
        raise PreviewError(f"Path non sicuro per book.json: {book_dir}")

    book_json_path = book_dir / BOOK_JSON_NAME

    if not book_json_path.exists():
        data = {
            "title": "Timmy KB",
            "author": "Pipeline",
            "plugins": []
        }
        try:
            book_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"📘 book.json generato in: {book_json_path}")
        except Exception as e:
            raise PreviewError(f"Errore generazione book.json: {e}")
    else:
        logger.info(f"📘 book.json già presente: {book_json_path}")


def ensure_package_json(book_dir: Path) -> None:
    """
    Garantisce la presenza di un file package.json nella directory markdown.
    """
    if not is_safe_subpath(book_dir, book_dir.parent):  # ✅ controllo path sicuro
        raise PreviewError(f"Path non sicuro per package.json: {book_dir}")

    package_json_path = book_dir / PACKAGE_JSON_NAME

    if not package_json_path.exists():
        data = {
            "name": "timmy-kb",
            "version": "1.0.0",
            "description": "Auto-generato per Honkit preview",
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
    context: ClientContext,
    port: int = 4000,
    container_name: str = "honkit_preview"
) -> None:
    """
    Avvia la preview GitBook/Honkit in Docker.
    """
    if not context.slug:
        raise PipelineError("Slug cliente mancante nel contesto per preview.")

    if not is_safe_subpath(context.md_dir, context.base_dir):  # ✅ controllo path sicuro
        raise PreviewError(f"Path markdown non sicuro: {context.md_dir}")

    md_output_path = context.md_dir.resolve()

    logger.info(f"📂 Directory per anteprima: {md_output_path}")

    # Creazione file necessari
    ensure_book_json(md_output_path)
    ensure_package_json(md_output_path)

    # Build statica
    build_cmd = [
        "docker", "run", "--rm",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npm", "run", "build"
    ]
    try:
        subprocess.run(build_cmd, check=True)
        logger.info("✅ Build statica Honkit completata.")
    except subprocess.CalledProcessError as e:
        logger.error("❌ Errore durante 'honkit build'.")
        raise PreviewError(f"Errore 'honkit build': {e}")

    # Servizio live preview
    serve_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:4000",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npm", "run", "serve"
    ]
    try:
        proc = subprocess.run(
            serve_cmd, check=True, capture_output=True, text=True
        )
        container_id = proc.stdout.strip()
        logger.info(f"🌍 Anteprima disponibile su: http://localhost:{port} (container: {container_id})")

        if not os.environ.get("BATCH_TEST"):
            input("⏹ Premi INVIO per chiudere l'anteprima e arrestare Docker...")
        subprocess.run(["docker", "stop", container_name], check=False)
        subprocess.run(["docker", "rm", "-f", container_name], check=False)

    except subprocess.CalledProcessError as e:
        logger.error("❌ Errore durante 'honkit serve'.")
        raise PreviewError(f"Errore 'honkit serve': {e}")
