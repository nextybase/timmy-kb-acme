# src/semantic/semantic_mapping.py
"""
Modulo per la gestione del file di mapping semantico nella pipeline Timmy-KB.
Refactor v1.0:
- Uso esclusivo di ClientContext
- Eliminato get_settings_for_slug
"""

from pathlib import Path
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import _validate_path_in_base_dir
from pipeline.exceptions import PipelineError
from pipeline.constants import SEMANTIC_MAPPING_FILE
from pipeline.context import ClientContext


def load_semantic_mapping(context: ClientContext, logger=None) -> dict:
    """
    Carica il file di mapping semantico per il cliente corrente.

    Args:
        context: ClientContext del cliente.
        logger: (opzionale) Logger strutturato.

    Returns:
        dict: Mapping semantico caricato dal file YAML.
    """
    logger = logger or get_structured_logger("semantic.mapping", context=context)

    mapping_path = context.config_dir / SEMANTIC_MAPPING_FILE
    _validate_path_in_base_dir(mapping_path, context.base_dir)

    if not mapping_path.exists():
        logger.error(f"❌ File di mapping semantico non trovato: {mapping_path}")
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_path}")

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        logger.info(f"📄 Mapping semantico caricato da {mapping_path}")
        return mapping
    except Exception as e:
        logger.error(f"❌ Errore lettura/parsing mapping {mapping_path}: {e}")
        raise PipelineError(f"Errore lettura mapping: {e}")
