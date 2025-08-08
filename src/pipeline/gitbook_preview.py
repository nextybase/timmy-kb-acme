"""
gitbook_preview.py

Strumenti per la generazione della preview locale del libro (GitBook/Honkit)
nella pipeline Timmy-KB, tramite container Docker isolato.
Gestisce la generazione automatica di book.json/package.json, build, preview,
e la pulizia del container anche in caso di errore/interruzione.
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Union
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PreviewError
from pipeline.config_utils import get_settings_for_slug  # <-- tolto import diretto settings

logger = get_structured_logger("pipeline.gitbook_preview", "logs/onboarding.log")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings.
    Se non viene passato esplicitamente, prova a usare get_settings_for_slug().
    """
    if settings is None:
        return get_settings_for_slug()
    return settings


def ensure_book_json(book_dir: Path) -> None:
    """Garantisce la presenza di un file book.json di base nella directory markdown."""
    book_json_path = book_dir / "book.json"
    if not book_json_path.exists():
        data = {
            "title": "Timmy KB",
            "author": "Pipeline",
            "plugins": []
        }
        book_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"📖 book.json generato in: {book_json_path}")
    else:
        logger.info(f"📖 book.json già presente: {book_json_path}")


def ensure_package_json(book_dir: Path) -> None:
    """Garantisce la presenza di un file package.json di base per la preview Honkit."""
    package_json_path = book_dir / "package.json"
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
        package_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"📦 package.json generato in: {package_json_path}")
    else:
        logger.info(f"📦 package.json già presente: {package_json_path}")


def run_gitbook_docker_preview(
    config: Union[dict, None] = None,
    port: int = 4000,
    container_name: str = "honkit_preview",
    settings=None
) -> None:
    """
    Avvia la preview GitBook/Honkit in Docker e garantisce la chiusura e rimozione
    del container al termine o in caso di errore/interruzione.
    """
    settings = _resolve_settings(settings)

    # Cleanup preventivo di eventuale container pre-esistente
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True, text=True, check=False
        )
        logger.info(f"🛑 (Pre-run) Docker container '{container_name}' rimosso se esistente.")
    except Exception as e:
        logger.warning(f"⚠️ (Pre-run) Impossibile rimuovere container Docker '{container_name}': {e}")

    # Determina la path markdown
    if config is None:
        md_output_path = settings.md_output_path.resolve()
    elif isinstance(config, dict):
        md_output_path = Path(config["md_output_path"]).resolve()
    else:
        md_output_path = Path(getattr(config, "md_output_path", settings.md_output_path)).resolve()

    logger.info(f"📦 Directory per anteprima: {md_output_path}")

    ensure_book_json(md_output_path)
    ensure_package_json(md_output_path)

    logger.info("🏗️ Build statica Honkit (Docker)...")
    build_cmd = [
        "docker", "run", "--rm",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npm", "run", "build"
    ]
    try:
        subprocess.run(build_cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("❌ Errore durante `honkit build`.")
        raise PreviewError(f"Errore `honkit build`: {e}")

    logger.info("🌐 Avvio anteprima GitBook (Docker live)...")
    serve_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:{port}",
        "--workdir", "/app",
        "-v", f"{md_output_path}:/app",
        "honkit/honkit", "npm", "run", "serve"
    ]
    container_id = None
    try:
        serve_proc = subprocess.run(serve_cmd, check=True, capture_output=True, text=True)
        container_id = serve_proc.stdout.strip()
        logger.info(f"🌍 Anteprima live avviata: http://localhost:{port} (container: {container_id})")
        if not os.environ.get("BATCH_TEST"):
            input("⏸️ Premi INVIO per chiudere l'anteprima e arrestare Docker...")
        else:
            logger.info("Modalità batch/CI: anteprima servita senza attesa interattiva.")
    except subprocess.CalledProcessError as e:
        logger.error(
            f"❌ Errore durante `honkit serve`: {e}\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
        )
        raise PreviewError(f"Errore `honkit serve`: {e}")
    finally:
        logger.info("🛑 Arresto container Docker...")
        try:
            subprocess.run(["docker", "stop", container_name], capture_output=True, text=True, check=False)
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True, check=False)
            logger.info(f"✅ Container Docker '{container_name}' rimosso.")
        except Exception as e:
            logger.error(f"⚠️ Errore nella rimozione del container Docker: {e}")
