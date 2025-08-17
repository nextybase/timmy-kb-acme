# src/pipeline/content_utils.py

"""
src/pipeline/content_utils.py

Utility per la generazione e validazione di file markdown a partire da PDF raw,
nell'ambito della pipeline Timmy-KB.
"""

import logging
from pathlib import Path
from typing import List, Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import safe_write_file  # ✅ Standard v1.0 stable
from pipeline.exceptions import PipelineError
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath  # ✅ Controllo sicurezza path

logger = get_structured_logger("pipeline.content_utils")


def convert_files_to_structured_markdown(
    context: ClientContext,
    raw_dir: Optional[Path] = None,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None
):
    """
    Converte i PDF presenti nella cartella raw in file markdown univoci per cartella.

    Args:
        context (ClientContext): contesto cliente con path e config.
        raw_dir (Path, opzionale): path alternativo alla cartella raw del contesto.
        md_dir (Path, opzionale): path alternativo alla cartella markdown.
        log (logger, opzionale): logger alternativo.

    Raises:
        PipelineError: se path non sicuro o errore in scrittura file.
    """
    raw_dir = raw_dir or context.raw_dir
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(f"Tentativo di scrivere file in path non sicuro: {md_dir}",
                            slug=context.slug, file_path=md_dir)
    md_dir.mkdir(parents=True, exist_ok=True)

    for subfolder in [p for p in raw_dir.iterdir() if p.is_dir()]:
        md_path = md_dir / f"{subfolder.name}.md"
        try:
            content = f"# {subfolder.name.capitalize()}\n\n"
            for pdf_file in sorted(subfolder.glob("*.pdf")):
                content += f"## {pdf_file.name}\n"
                content += f"(Contenuto estratto/conversione da {pdf_file.name}...)\n\n"

            local_logger.info(f"Creazione file markdown aggregato: {md_path}",
                              extra={"slug": context.slug, "file_path": md_path})
            safe_write_file(md_path, content)
            local_logger.info(f"File markdown scritto correttamente: {md_path}",
                              extra={"slug": context.slug, "file_path": md_path})
        except Exception as e:
            local_logger.error(f"Errore nella creazione markdown {md_path}: {e}",
                               extra={"slug": context.slug, "file_path": md_path})
            raise PipelineError(str(e), slug=context.slug, file_path=md_path)


def generate_summary_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None
):
    """Genera il file SUMMARY.md nella directory markdown."""
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(f"Tentativo di scrivere file in path non sicuro: {md_dir}",
                            slug=context.slug, file_path=md_dir)

    summary_path = md_dir / "SUMMARY.md"
    try:
        content = "# Summary\n\n"
        for md_file in sorted(md_dir.glob("*.md")):
            if md_file.name not in ("SUMMARY.md", "README.md"):
                content += f"* [{md_file.stem}]({md_file.name})\n"

        local_logger.info(f"Generazione SUMMARY.md in {summary_path}",
                          extra={"slug": context.slug, "file_path": summary_path})
        safe_write_file(summary_path, content)
        local_logger.info("SUMMARY.md generato con successo.",
                          extra={"slug": context.slug, "file_path": summary_path})
    except Exception as e:
        local_logger.error(f"Errore generazione SUMMARY.md: {e}",
                           extra={"slug": context.slug, "file_path": summary_path})
        raise PipelineError(str(e), slug=context.slug, file_path=summary_path)


def generate_readme_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None
):
    """Genera il file README.md nella directory markdown."""
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(f"Tentativo di scrivere file in path non sicuro: {md_dir}",
                            slug=context.slug, file_path=md_dir)

    readme_path = md_dir / "README.md"
    try:
        content = "# Documentazione Timmy-KB\n"
        local_logger.info(f"Generazione README.md in {readme_path}",
                          extra={"slug": context.slug, "file_path": readme_path})
        safe_write_file(readme_path, content)
        local_logger.info("README.md generato con successo.",
                          extra={"slug": context.slug, "file_path": readme_path})
    except Exception as e:
        local_logger.error(f"Errore generazione README.md: {e}",
                           extra={"slug": context.slug, "file_path": readme_path})
        raise PipelineError(str(e), slug=context.slug, file_path=readme_path)


def validate_markdown_dir(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None
):
    """Verifica che la directory markdown esista e sia valida."""
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(f"Tentativo di accedere a un path non sicuro: {md_dir}",
                            slug=context.slug, file_path=md_dir)

    if not md_dir.exists():
        local_logger.error(f"La cartella markdown non esiste: {md_dir}",
                           extra={"slug": context.slug, "file_path": md_dir})
        raise FileNotFoundError(f"La cartella markdown non esiste: {md_dir}")
    if not md_dir.is_dir():
        local_logger.error(f"Il path non è una directory: {md_dir}",
                           extra={"slug": context.slug, "file_path": md_dir})
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")
