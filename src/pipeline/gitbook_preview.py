"""
gitbook_preview.py

Strumenti per la generazione della preview locale del libro (GitBook/Honkit)  
nella pipeline Timmy-KB, tramite container Docker isolato.  
Gestisce la generazione automatica di book.json/package.json, build, preview,  
e la pulizia del container anche in caso di errore/interruzione.
"""

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
    Garantisce la presenza di un file book.json di base nella directory markdown.

    Args:
        book_dir (Path): Directory markdown del progetto.
    """
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
    """
    Garantisce la presenza di un file package.json di base per la preview Honkit.

    Args:
        book_dir (Path): Directory markdown del progetto.
    """
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
    config: Union[dict, TimmyConfig],
    port: int = 4000,
    container_name: str = "honkit_preview"
) -> None:
    """
    Avvia la preview GitBook/Honkit in Docker e garantisce la chiusura e la rimozione
    del container al termine, anche in caso di errore o interruzione.
    Rimuove sempre ogni residuo preesistente con lo stesso nome container.

    Args:
        config (dict | TimmyConfig): Configurazione pipeline (usata per md_output_path).
        port (int, optional): Porta di pubblicazione locale (default 4000).
        container_name (str, optional): Nome container Docker temporaneo.

    Raises:
        PreviewError: In caso di errore nel build/serve della preview.
    """
    # Cleanup preventivo di eventuale container pre-esistente (anche Exited)
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True, text=True, check=False
        )
        logger.info(f"🧹 (Pre-run) Docker container '{container_name}' rimosso se esistente.")
    except Exception as e:
        logger.warning(f"⚠️ (Pre-run) Impossibile rimuovere container Docker '{container_name}': {e}")

    if isinstance(config, dict):
        md_output_path = Path(config["md_output_path"]).resolve()
    else:
        md_output_path = config.md_output_path_path.resolve()

    logger.info(f"📦 Directory per anteprima: {md_output_path}")

    ensure_book_json(md_output_path)
    ensure_package_json(md_output_path)

    logger.info("🛠️  Build statico Honkit (Docker)...")
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

    logger.info("🔄 Avvio anteprima GitBook (Docker serve live)...")
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
        input("🔄 Premi INVIO per chiudere l'anteprima e arrestare Docker...")
    except subprocess.CalledProcessError as e:
        logger.error(
            f"❌ Errore durante `honkit serve`: {e}\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
        )
        raise PreviewError(f"Errore `honkit serve`: {e}")
    finally:
        logger.info("💕 Arresto container Docker...")
        try:
            # Prova prima con stop
            stop_proc = subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True, text=True, check=False
            )
            logger.info(f"🛑 Docker stop stdout: {stop_proc.stdout.strip()}")
            logger.info(f"🛑 Docker stop stderr: {stop_proc.stderr.strip()}")
            if stop_proc.returncode != 0:
                logger.warning("🛑 Docker stop non riuscito, provo con 'docker kill'")
                kill_proc = subprocess.run(
                    ["docker", "kill", container_name],
                    capture_output=True, text=True, check=False
                )
                logger.info(f"🛑 Docker kill stdout: {kill_proc.stdout.strip()}")
                logger.info(f"🛑 Docker kill stderr: {kill_proc.stderr.strip()}")
            # Pulizia finale anche di container exited
            rm_proc = subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True, text=True, check=False
            )
            logger.info(f"🧹 Docker rm stdout: {rm_proc.stdout.strip()}")
            logger.info(f"🧹 Docker rm stderr: {rm_proc.stderr.strip()}")
            logger.info(f"🧹 Docker container '{container_name}' rimosso (se presente).")
        except Exception as e:
            logger.error(f"⚠️ Errore durante la rimozione del container Docker: {e}")
