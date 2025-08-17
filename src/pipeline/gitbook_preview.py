# src/pipeline/gitbook_preview.py
"""
Genera e avvia la preview locale della documentazione (GitBook/HonKit)
usando container Docker isolato.

Note:
- Nessuna terminazione del processo: in caso di errori solleva `PreviewError`/`PipelineError`.
- Path-safety: tutti i percorsi sono verificati prima dell'uso.
"""

from __future__ import annotations

import subprocess
import json
from pathlib import Path
from typing import Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PreviewError, PipelineError
from pipeline.constants import BOOK_JSON_NAME, PACKAGE_JSON_NAME
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath

logger = get_structured_logger("pipeline.gitbook_preview")


def ensure_book_json(book_dir: Path, slug: Optional[str] = None) -> None:
    """Garantisce la presenza di un file `book.json` nella directory markdown.

    Verifica path-safety rispetto al parent e crea un `book.json` minimale se assente.

    Args:
        book_dir: Directory markdown (root del libro HonKit).
        slug: Identificativo cliente per contestualizzare i log.

    Raises:
        PreviewError: se il percorso non è sicuro o in caso di I/O fallito.
    """
    if not is_safe_subpath(book_dir, book_dir.parent):
        raise PreviewError(
            f"Path non sicuro per book.json: {book_dir}",
            slug=slug,
            file_path=book_dir,
        )

    book_json_path = book_dir / BOOK_JSON_NAME

    if not book_json_path.exists():
        data = {
            "title": "Timmy KB",
            "author": "Pipeline",
            "plugins": [],
        }
        try:
            book_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info("📘 book.json generato", extra={"slug": slug, "file_path": str(book_json_path)})
        except Exception as e:
            raise PreviewError(f"Errore generazione book.json: {e}", slug=slug, file_path=book_json_path)
    else:
        logger.info("📘 book.json già presente", extra={"slug": slug, "file_path": str(book_json_path)})


def ensure_package_json(book_dir: Path, slug: Optional[str] = None) -> None:
    """Garantisce la presenza di un file `package.json` nella directory markdown.

    Verifica path-safety rispetto al parent e crea un `package.json` minimale se assente.

    Args:
        book_dir: Directory markdown (root del libro HonKit).
        slug: Identificativo cliente per contestualizzare i log.

    Raises:
        PreviewError: se il percorso non è sicuro o in caso di I/O fallito.
    """
    if not is_safe_subpath(book_dir, book_dir.parent):
        raise PreviewError(
            f"Path non sicuro per package.json: {book_dir}",
            slug=slug,
            file_path=book_dir,
        )

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
                "serve": "honkit serve",
            },
        }
        try:
            package_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info("📦 package.json generato", extra={"slug": slug, "file_path": str(package_json_path)})
        except Exception as e:
            raise PreviewError(f"Errore generazione package.json: {e}", slug=slug, file_path=package_json_path)
    else:
        logger.info("📦 package.json già presente", extra={"slug": slug, "file_path": str(package_json_path)})


def run_gitbook_docker_preview(
    context: ClientContext,
    port: int = 4000,
    container_name: str = "honkit_preview",
    wait_on_exit: bool = True,
) -> None:
    """Avvia la preview GitBook/HonKit in Docker.

    Comportamento:
        - Genera `book.json` e `package.json` minimi se mancanti.
        - Esegue `honkit build` in container.
        - Avvia `honkit serve` mappando la porta locale.
        - Se `wait_on_exit` è True, attende un invio da tastiera e poi arresta/rimuove il container.

    Args:
        context: Contesto cliente con `slug`, `md_dir`, `base_dir`.
        port: Porta locale da esporre (default 4000).
        container_name: Nome del container Docker da usare.
        wait_on_exit: Se False, non attende input e non interrompe il container.

    Raises:
        PipelineError: se `slug` mancante nel contesto.
        PreviewError: se i path non sono sicuri o in caso di errori di build/serve.
    """
    if not context.slug:
        raise PipelineError("Slug cliente mancante nel contesto per preview", slug=None)

    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PreviewError(
            f"Percorso markdown non sicuro: {context.md_dir}",
            slug=context.slug,
            file_path=context.md_dir,
        )

    md_output_path = context.md_dir.resolve()

    logger.info("📂 Directory per anteprima", extra={"slug": context.slug, "file_path": str(md_output_path)})

    # Creazione file necessari (idempotente)
    ensure_book_json(md_output_path, slug=context.slug)
    ensure_package_json(md_output_path, slug=context.slug)

    # Build statica
    build_cmd = [
        "docker",
        "run",
        "--rm",
        "--workdir",
        "/app",
        "-v",
        f"{md_output_path}:/app",
        "honkit/honkit",
        "npm",
        "run",
        "build",
    ]
    try:
        subprocess.run(build_cmd, check=True)
        logger.info("🔨 Build statica HonKit completata.", extra={"slug": context.slug})
    except subprocess.CalledProcessError as e:
        logger.error("❌ Errore durante 'honkit build'", extra={"slug": context.slug})
        raise PreviewError(f"Errore 'honkit build': {e}", slug=context.slug)

    # Avvio live preview
    serve_cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "-p",
        f"{port}:4000",
        "--workdir",
        "/app",
        "-v",
        f"{md_output_path}:/app",
        "honkit/honkit",
        "npm",
        "run",
        "serve",
    ]
    try:
        proc = subprocess.run(serve_cmd, check=True, capture_output=True, text=True)
        container_id = proc.stdout.strip()
        logger.info(
            f"🌐 Anteprima su http://localhost:{port} (container: {container_id})",
            extra={"slug": context.slug},
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
