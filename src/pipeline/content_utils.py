"""
Utility per la generazione e validazione di file markdown a partire dai PDF raw,
nell'ambito della pipeline Timmy-KB.

Modifiche Fase 1:
- Uso costanti centralizzate (constants.py) per nomi directory/file.
- Integrazione con BASE_DIR da config_utils.py.
- Backup e scrittura sicura dei file markdown.
"""

from pathlib import Path
from typing import List
import shutil
from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug
from pipeline.constants import BACKUP_SUFFIX
from pipeline.exceptions import PipelineError

logger = get_structured_logger("pipeline.content_utils")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings.
    Se non viene passato esplicitamente, usa get_settings_for_slug().
    """
    if settings is None:
        return get_settings_for_slug()
    return settings


def _safe_write_file(file_path: Path, content: str):
    """
    Scrive un file in modo sicuro:
    - Backup del file esistente
    - Sovrascrittura con nuovo contenuto
    """
    if file_path.exists():
        backup_path = file_path.with_suffix(BACKUP_SUFFIX)
        shutil.copy(file_path, backup_path)
        logger.info(f"Backup creato: {backup_path}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.debug(f"File scritto: {file_path}")


def convert_files_to_structured_markdown(settings=None):
    """
    Aggrega i PDF presenti nella cartella settings.raw_dir in un file markdown unico
    per cartella, nella cartella settings.md_output_path.
    """
    settings = _resolve_settings(settings)
    md_dir = settings.md_output_path
    raw_dir = settings.raw_dir
    md_dir.mkdir(parents=True, exist_ok=True)

    for subfolder in [p for p in raw_dir.iterdir() if p.is_dir()]:
        md_path = md_dir / f"{subfolder.name}.md"
        try:
            content = f"# {subfolder.name.capitalize()}\n\n"
            for pdf_file in sorted(subfolder.glob("*.pdf")):
                content += f"## {pdf_file.name}\n"
                content += f"(Contenuto estratto/conversione da {pdf_file.name} qui...)\n\n"

            _safe_write_file(md_path, content)
            logger.info(f"Creato file markdown aggregato: {md_path}")
        except Exception as e:
            logger.error(f"Errore nella creazione del file markdown {md_path}: {e}")
            raise PipelineError(f"Errore nella creazione di {md_path}") from e


def generate_summary_markdown(md_files: List[Path], md_dir: Path = None, settings=None):
    """
    Genera il file SUMMARY.md nella directory markdown.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    summary_path = md_dir / "SUMMARY.md"
    try:
        content = "# Summary\n\n"
        for md_file in md_files:
            content += f"* [{md_file.stem}]({md_file.name})\n"

        _safe_write_file(summary_path, content)
        logger.info(f"Generato SUMMARY.md in {summary_path}")
    except Exception as e:
        logger.error(f"Errore nella generazione di SUMMARY.md: {e}")
        raise PipelineError(f"Errore nella generazione di SUMMARY.md") from e


def generate_readme_markdown(md_dir: Path = None, settings=None):
    """
    Genera il file README.md nella directory markdown.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    readme_path = md_dir / "README.md"
    try:
        content = "# Documentazione Timmy-KB\n"
        _safe_write_file(readme_path, content)
        logger.info(f"Generato README.md in {readme_path}")
    except Exception as e:
        logger.error(f"Errore nella generazione di README.md: {e}")
        raise PipelineError(f"Errore nella generazione di README.md") from e


def validate_markdown_dir(md_dir: Path = None, settings=None):
    """
    Verifica che la directory markdown esista e sia valida.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    if not md_dir.exists():
        logger.error(f"La cartella markdown non esiste: {md_dir}")
        raise FileNotFoundError(f"La cartella markdown non esiste: {md_dir}")
    if not md_dir.is_dir():
        logger.error(f"Il path non è una directory: {md_dir}")
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")
