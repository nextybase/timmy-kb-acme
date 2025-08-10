"""
semantic_mapping.py

Modulo per la gestione del file di mapping semantico nella pipeline Timmy-KB.
"""

from pathlib import Path
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug, _validate_path_in_base_dir
from pipeline.exceptions import PipelineError
from pipeline.constants import SEMANTIC_MAPPING_FILE


def load_semantic_mapping(slug: str, logger=None) -> dict:
    """
    Carica il file di mapping semantico per uno slug specifico.

    Args:
        slug (str): Slug del cliente.
        logger (Logger, opzionale): Logger strutturato da usare.

    Returns:
        dict: Mapping semantico caricato dal file YAML.
    """
    if logger is None:
        logger = get_structured_logger("semantic.mapping")

    settings = get_settings_for_slug(slug)
    mapping_path = settings.config_dir / SEMANTIC_MAPPING_FILE

    # 🔍 DEBUG extra per capire path reale
    logger.debug(f"[DEBUG] settings.config_dir = {settings.config_dir}")
    logger.debug(f"[DEBUG] SEMANTIC_MAPPING_FILE = {SEMANTIC_MAPPING_FILE}")
    logger.debug(f"[DEBUG] mapping_path calcolato = {mapping_path}")

    _validate_path_in_base_dir(mapping_path, settings.config_dir)

    if not mapping_path.exists():
        logger.error(f"❌ File di mapping semantico non trovato: {mapping_path}")
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_path}")

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        logger.info(f"📄 Mapping semantico caricato da {mapping_path}")
        return mapping
    except Exception as e:
        logger.error(f"❌ Errore nella lettura/parsing di {mapping_path}: {e}")
        raise PipelineError(f"Errore lettura mapping: {e}")
