"""
content_utils.py

Utility per la generazione e validazione di file markdown a partire dai PDF raw,
nell'ambito della pipeline Timmy-KB.
Permette la conversione automatica, la generazione di file di sommario/documentazione
e la validazione della directory di output.
"""

from pathlib import Path
from typing import List
from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug

logger = get_structured_logger("pipeline.content_utils")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings.
    Se non viene passato esplicitamente, prova a usare get_settings_for_slug().
    """
    if settings is None:
        return get_settings_for_slug()
    return settings


def convert_files_to_structured_markdown(settings=None):
    """
    Aggrega i PDF presenti nella cartella settings.raw_dir in un file markdown unico per cartella,
    nella cartella settings.md_output_path.
    Ogni file .md prende il nome della cartella di origine.
    """
    settings = _resolve_settings(settings)
    md_dir = settings.md_output_path
    raw_dir = settings.raw_dir
    md_dir.mkdir(parents=True, exist_ok=True)

    for subfolder in [p for p in raw_dir.iterdir() if p.is_dir()]:
        md_path = md_dir / f"{subfolder.name}.md"
        try:
            with open(md_path, "w", encoding="utf-8") as out_md:
                out_md.write(f"# {subfolder.name.capitalize()}\n\n")
                for pdf_file in sorted(subfolder.glob("*.pdf")):
                    out_md.write(f"## {pdf_file.name}\n")
                    out_md.write(f"(Contenuto estratto/conversione da {pdf_file.name} qui...)\n\n")
            logger.info(f"✅ Creato file markdown aggregato: {md_path}")
        except Exception as e:
            logger.error(f"❌ Errore nella creazione del file markdown {md_path}: {e}")


def generate_summary_markdown(md_files: List[Path], md_dir: Path = None, settings=None):
    """
    Genera il file SUMMARY.md nella directory markdown.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    summary_path = md_dir / "SUMMARY.md"
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("# Summary\n\n")
            for md_file in md_files:
                f.write(f"* [{md_file.stem}]({md_file.name})\n")
        logger.info(f"📝 Generato SUMMARY.md in {summary_path}")
    except Exception as e:
        logger.error(f"❌ Errore nella generazione di SUMMARY.md: {e}")


def generate_readme_markdown(md_dir: Path = None, settings=None):
    """
    Genera il file README.md nella directory markdown.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    readme_path = md_dir / "README.md"
    try:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("# Documentazione Timmy-KB\n")
        logger.info(f"📝 Generato README.md in {readme_path}")
    except Exception as e:
        logger.error(f"❌ Errore nella generazione di README.md: {e}")


def validate_markdown_dir(md_dir: Path = None, settings=None):
    """
    Verifica che la directory markdown esista e sia valida.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    if not md_dir.exists():
        logger.error(f"❌ La cartella markdown non esiste: {md_dir}")
        raise FileNotFoundError(f"La cartella markdown non esiste: {md_dir}")
    if not md_dir.is_dir():
        logger.error(f"❌ Il path non è una directory: {md_dir}")
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")
