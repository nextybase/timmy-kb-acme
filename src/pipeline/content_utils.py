"""
content_utils.py

Utility per la generazione e validazione di file markdown a partire da PDF raw,
nell'ambito della pipeline Timmy-KB.

Modifiche Fase 2:
- Validazione path sicura con _validate_path_in_base_dir
- Uso costanti da constants.py
- Logger e messaggi uniformati
- Gestione eccezioni uniforme
"""

from pathlib import Path
from typing import List, Optional, Union
import shutil

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug
from pipeline.constants import BACKUP_SUFFIX
from pipeline.exceptions import PipelineError
from pipeline.utils import _validate_path_in_base_dir

logger = get_structured_logger("pipeline.content_utils")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings valida.
    Se non viene passato esplicitamente, solleva errore chiaro.
    Evita di interpretare per errore logger o altri oggetti come settings.
    """
    if settings is None:
        raise PipelineError(
            "Parametro 'settings' mancante. "
            "Fornire un oggetto Settings valido alla funzione chiamante."
        )
    if not hasattr(settings, "logs_path") or not hasattr(settings, "base_dir"):
        raise PipelineError(
            "Oggetto 'settings' non valido: atteso Settings con 'logs_path' e 'base_dir'."
        )
    return settings


def _safe_write_file(file_path: Path, content: str):
    """
    Scrive un file in modo sicuro:
    - Backup del file esistente
    - Sovrascrittura con nuovo contenuto
    """
    _validate_path_in_base_dir(file_path, file_path.parent)

    if file_path.exists():
        backup_path = file_path.with_suffix(BACKUP_SUFFIX)
        shutil.copy(file_path, backup_path)
        logger.info(f"💾 Backup creato: {backup_path}")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug(f"✏️ File scritto: {file_path}")
    except Exception as e:
        logger.error(f"❌ Errore scrittura file {file_path}: {e}")
        raise PipelineError(f"Errore scrittura file {file_path}: {e}")


def convert_files_to_structured_markdown(
    arg1: Optional[Union[Path, object]] = None,
    arg2: Optional[Path] = None,
    arg3=None
):
    """
    Converte i PDF presenti nella cartella raw in file markdown univoci per cartella.
    Supporta due modalità:
    1. Vecchio stile: convert_files_to_structured_markdown(settings)
    2. Nuovo stile: convert_files_to_structured_markdown(raw_dir, md_output_path, logger)
    """
    if isinstance(arg1, Path) and isinstance(arg2, Path):
        # Nuovo stile
        raw_dir = arg1
        md_dir = arg2
        local_logger = arg3 or logger
        settings = None
    else:
        # Vecchio stile
        settings = _resolve_settings(arg1)
        raw_dir = settings.raw_dir
        md_dir = settings.md_output_path
        local_logger = logger

    # Validazione path sicura
    if settings:
        _validate_path_in_base_dir(md_dir, settings.base_dir)
    else:
        _validate_path_in_base_dir(md_dir, md_dir.parent)

    md_dir.mkdir(parents=True, exist_ok=True)

    for subfolder in [p for p in raw_dir.iterdir() if p.is_dir()]:
        md_path = md_dir / f"{subfolder.name}.md"
        try:
            content = f"# {subfolder.name.capitalize()}\n\n"
            for pdf_file in sorted(subfolder.glob("*.pdf")):
                content += f"## {pdf_file.name}\n"
                content += f"(Contenuto estratto/conversione da {pdf_file.name}...)\n\n"

            _safe_write_file(md_path, content)
            local_logger.info(f"📄 Creato file markdown aggregato: {md_path}")
        except Exception as e:
            local_logger.error(f"❌ Errore creazione file markdown {md_path}: {e}")
            raise PipelineError(f"Errore creazione markdown {md_path}: {e}")


def generate_summary_markdown(md_files: List[Path], md_dir: Path = None, settings=None):
    """
    Genera il file SUMMARY.md nella directory markdown.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    summary_path = md_dir / "SUMMARY.md"
    try:
        _validate_path_in_base_dir(summary_path, summary_path.parent)
        content = "# Summary\n\n"
        for md_file in md_files:
            content += f"* [{md_file.stem}]({md_file.name})\n"

        _safe_write_file(summary_path, content)
        logger.info(f"📑 Generato SUMMARY.md in {summary_path}")
    except Exception as e:
        logger.error(f"❌ Errore generazione SUMMARY.md: {e}")
        raise PipelineError("Errore generazione SUMMARY.md")


def generate_readme_markdown(md_dir: Path = None, settings=None):
    """
    Genera il file README.md nella directory markdown.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    readme_path = md_dir / "README.md"
    try:
        _validate_path_in_base_dir(readme_path, readme_path.parent)
        content = "# Documentazione Timmy-KB\n"
        _safe_write_file(readme_path, content)
        logger.info(f"📘 Generato README.md in {readme_path}")
    except Exception as e:
        logger.error(f"❌ Errore generazione README.md: {e}")
        raise PipelineError("Errore generazione README.md")


def validate_markdown_dir(md_dir: Path = None, settings=None):
    """
    Verifica che la directory markdown esista e sia valida.
    """
    settings = _resolve_settings(settings)
    if md_dir is None:
        md_dir = settings.md_output_path

    _validate_path_in_base_dir(md_dir, md_dir.parent)

    if not md_dir.exists():
        logger.error(f"❌ La cartella markdown non esiste: {md_dir}")
        raise FileNotFoundError(f"La cartella markdown non esiste: {md_dir}")
    if not md_dir.is_dir():
        logger.error(f"❌ Il path non è una directory: {md_dir}")
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")
