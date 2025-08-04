from pathlib import Path
from typing import List
import logging

logger = logging.getLogger("pipeline.content_utils")


def convert_files_to_structured_markdown(config, mapping: dict):
    """
    Converte i PDF presenti in config.raw_dir_path in markdown strutturati
    nella cartella config.md_output_path_path, ignorando la struttura delle sottocartelle.

    Args:
        config: Oggetto di configurazione con attributi .md_output_path_path e .raw_dir_path
        mapping: Dizionario semantico per la conversione (placeholder)
    """
    md_dir = config.md_output_path_path
    raw_dir = config.raw_dir_path
    md_dir.mkdir(parents=True, exist_ok=True)

    for pdf_file in raw_dir.rglob("*.pdf"):
        # Crea un nome unico basato sulla sottocartella, se presente
        stem = pdf_file.stem
        if pdf_file.parent != raw_dir:
            rel_parts = pdf_file.parent.relative_to(raw_dir).parts
            prefix = "-".join(rel_parts)
            stem = f"{prefix}_{stem}"

        md_path = md_dir / f"{stem}.md"
        with open(md_path, "w", encoding="utf-8") as out_md:
            out_md.write(f"# Markdown per {pdf_file.name}\n")
        logger.info(f"✅ Creato file markdown: {md_path}")


def generate_summary_markdown(md_files: List[Path], md_dir: Path):
    """
    Genera il file SUMMARY.md nella directory markdown.

    Args:
        md_files: Lista di Path dei file markdown
        md_dir: Directory in cui salvare SUMMARY.md
    """
    summary_path = md_dir / "SUMMARY.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# Summary\n\n")
        for md_file in md_files:
            f.write(f"* [{md_file.stem}]({md_file.name})\n")
    logger.info(f"📘 Generato SUMMARY.md in {summary_path}")


def generate_readme_markdown(md_dir: Path):
    """
    Genera il file README.md nella directory markdown.

    Args:
        md_dir: Directory in cui salvare README.md
    """
    readme_path = md_dir / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# Documentazione Timmy-KB\n")
    logger.info(f"📘 Generato README.md in {readme_path}")


def validate_markdown_dir(md_dir: Path):
    """
    Verifica che la directory markdown esista e sia una directory valida.

    Args:
        md_dir: Path della directory markdown

    Raises:
        FileNotFoundError: se la directory non esiste
        NotADirectoryError: se il path non è una directory
    """
    if not md_dir.exists():
        raise FileNotFoundError(f"La cartella markdown non esiste: {md_dir}")
    if not md_dir.is_dir():
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")
