# src/pipeline/gitbook_preview.py
"""
Genera e avvia la preview locale della documentazione (GitBook/HonKit)
usando container Docker isolato.
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
from pipeline.path_utils import is_safe_subpath

logger = get_structured_logger("pipeline.gitbook_preview")


def ensure_book_json(book_dir: Path, slug: str = None) -> None:
    """Garantisce la presenza di un file book.json nella directory markdown."""
    if not is_safe_subpath(book_dir, book_dir.parent):
        raise PreviewError(f"Path non sicuro per book.json: {book_dir}",
                           slug=slug, file_path=book_dir)

    book_json_path = book_dir / BOOK_JSON_NAME

    if not book_json_path.exists():
        data = {
            "title": "Timmy KB",
            "author": "Pipeline",
            "plugins": []
        }
        try:
            book_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"📘 book.json generato in: {book_json_path}", extra={"slug": slug})
        except Exception as e:
            raise PreviewError(f"Errore generazione book.json: {e}", slug=slug, file_path=book_json_path)
    else:
        logger.info(f"📘 book.json già presente: {book_json_path}", extra={"slug": slug})


def ensure_package_json(book_dir: Path, slug: str = None) -> None:
    """Garantisce la presenza di un file package.json nella directory markdown."""
    if not is_safe_subpath(book_dir, book_dir.parent):
        raise PreviewError(f"Path non sicuro per package.json: {book_dir}",
                           slug=slug, file_path=book_dir)

    package_json_path = book_dir / PACKAGE_JSON_NAME

    if not package_json_path.exists():
        data = {
            "name": "timmy-kb",
            "version": "1.0.0",
            "description": "Auto-generato per HonKit preview",
            "main": "README.md",
            "license": "MIT",
            "scripts": {
                "build": "honkit build",
                "serve": "honkit serve"
            }
        }
        try:
            package_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"📦 package.json generato in: {package_json_path}", extra={"slug": slug})
        except Exception as e:
            raise PreviewError(f"Errore generazione package.json: {e}", slug=slug, file_path=package_json_path)
    else:
        logger.info(f"📦 package.json già presente: {package_json_path}", extra={"slug": slug})


def run_gitbook_docker_preview(
    context: ClientContext,
    port: int = 4000,
    container_name: str = "honkit_preview",
    wait_on_exit: bool = True
) -> None:
    """
    Avvia la preview GitBook/HonKit in Docker.
    Se wait_on_exit è False, chiude automaticamente senza richiedere input.
    """
    if not context.slug:
        raise PipelineError("Slug cliente mancante nel contesto per preview", slug=None)

    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PreviewError(f"Percorso markdown non sicuro: {context.md_dir}",
                           slug=context.slug, file_path=context.md_dir)

    md_output_path = context.md_dir.resolve()

    logger.info(f"📂 Directory per anteprima: {md_output_path}", extra={"slug": context.slug})

    # Creazione file necessari
    ensure_book_json(md_output_path, slug=context.slug)
    ensure_package_json(md_output_path, slug=context.slug)

    # Build statica
    build_cmd = [
        "docker", "run", "--rm",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npm", "run", "build"
    ]
    try:
        subprocess.run(build_cmd, check=True)
        logger.info("🔨 Build statica HonKit completata.", extra={"slug": context.slug})
    except subprocess.CalledProcessError as e:
        logger.error("❌ Errore durante 'honkit build'", extra={"slug": context.slug})
        raise PreviewError(f"Errore 'honkit build': {e}", slug=context.slug)

    # Avvio live preview
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
        logger.info(
            f"🌐 Anteprima disponibile su: http://localhost:{port} (container: {container_id})",
            extra={"slug": context.slug}
        )

        if wait_on_exit:
            input("👉 Premi INVIO per chiudere anteprima e arrestare Docker...")
            subprocess.run(["docker", "stop", container_name], check=False)
            subprocess.run(["docker", "rm", container_name], check=False)
            logger.info("🛑 Preview GitBook terminata.", extra={"slug": context.slug})
        else:
            logger.info("Modalità batch: preview avviata senza attesa", extra={"slug": context.slug})

    except subprocess.CalledProcessError as e:
        logger.error("❌ Errore durante 'honkit serve'", extra={"slug": context.slug})
        raise PreviewError(f"Errore 'honkit serve': {e}", slug=context.slug)
