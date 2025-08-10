# src/pipeline/content_utils.py
"""
Utility per la generazione e validazione di file markdown a partire da PDF raw,
nell'ambito della pipeline Timmy-KB.
"""

from pathlib import Path
from typing import List, Optional, Union

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import (
    _validate_path_in_base_dir,
    _safe_write_file
)
from pipeline.exceptions import PipelineError
from pipeline.context import ClientContext

logger = get_structured_logger("pipeline.content_utils")

def convert_files_to_structured_markdown(
    context: ClientContext,
    raw_dir: Optional[Path] = None,
    md_dir: Optional[Path] = None,
    log: Optional[object] = None
):
    """
    Converte i PDF presenti nella cartella raw in file markdown univoci per cartella.
    """
    raw_dir = raw_dir or context.raw_dir
    md_dir = md_dir or context.md_dir
    local_logger = log or get_structured_logger("pipeline.content_utils")

    _validate_path_in_base_dir(md_dir, context.base_dir)
    md_dir.mkdir(parents=True, exist_ok=True)

    for subfolder in [p for p in raw_dir.iterdir() if p.is_dir()]:
        md_path = md_dir / f"{subfolder.name}.md"
        try:
            content = f"# {subfolder.name.capitalize()}\n\n"
            for pdf_file in sorted(subfolder.glob("*.pdf")):
                content += f"## {pdf_file.name}\n"
                content += f"(Contenuto estratto/conversione da {pdf_file.name}...)\n\n"

            _safe_write_file(md_path, content, logger=local_logger)
            local_logger.info(f"✅ Creato file markdown aggregato: {md_path}")
        except Exception as e:
            local_logger.error(f"❌ Errore creazione markdown {md_path}: {e}")
            raise PipelineError(f"Errore creazione markdown {md_path}: {e}")

def generate_summary_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[object] = None
):
    """
    Genera il file SUMMARY.md nella directory markdown.
    """
    md_dir = md_dir or context.md_dir
    local_logger = log or get_structured_logger("pipeline.content_utils")

    _validate_path_in_base_dir(md_dir, context.base_dir)

    summary_path = md_dir / "SUMMARY.md"
    try:
        content = "# Summary\n\n"
        for md_file in sorted(md_dir.glob("*.md")):
            if md_file.name not in ("SUMMARY.md", "README.md"):
                content += f"* [{md_file.stem}]({md_file.name})\n"

        _safe_write_file(summary_path, content, logger=local_logger)
        local_logger.info(f"✅ Generato SUMMARY.md in {summary_path}")
    except Exception as e:
        local_logger.error(f"❌ Errore generazione SUMMARY.md: {e}")
        raise PipelineError("Errore generazione SUMMARY.md")

def generate_readme_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[object] = None
):
    """
    Genera il file README.md nella directory markdown.
    """
    md_dir = md_dir or context.md_dir
    local_logger = log or get_structured_logger("pipeline.content_utils")

    _validate_path_in_base_dir(md_dir, context.base_dir)

    readme_path = md_dir / "README.md"
    try:
        content = "# Documentazione Timmy-KB\n"
        _safe_write_file(readme_path, content, logger=local_logger)
        local_logger.info(f"✅ Generato README.md in {readme_path}")
    except Exception as e:
        local_logger.error(f"❌ Errore generazione README.md: {e}")
        raise PipelineError("Errore generazione README.md")

def validate_markdown_dir(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[object] = None
):
    """
    Verifica che la directory markdown esista e sia valida.
    """
    md_dir = md_dir or context.md_dir
    local_logger = log or get_structured_logger("pipeline.content_utils")

    _validate_path_in_base_dir(md_dir, context.base_dir)

    if not md_dir.exists():
        local_logger.error(f"❌ La cartella markdown non esiste: {md_dir}")
        raise FileNotFoundError(f"La cartella markdown non esiste: {md_dir}")
    if not md_dir.is_dir():
        local_logger.error(f"❌ Il path non è una directory: {md_dir}")
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")
