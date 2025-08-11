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
from pipeline.path_utils import is_safe_subpath  # ✅ nuovo import
from pipeline.exceptions import PipelineError, FileNotFoundError
from pipeline.constants import SEMANTIC_MAPPING_FILE
from pipeline.context import ClientContext

logger = get_structured_logger("semantic.mapping")

# ✅ schema minimo di validazione
REQUIRED_MAPPING_KEYS = {"concepts"}  # esempio: deve contenere almeno "concepts" come chiave di primo livello


def _validate_mapping_schema(mapping: dict) -> bool:
    """
    Verifica che il mapping rispetti lo schema minimo richiesto.
    """
    if not isinstance(mapping, dict):
        return False
    return REQUIRED_MAPPING_KEYS.issubset(mapping.keys())


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
    if not is_safe_subpath(mapping_path, context.base_dir):  # ✅ controllo path sicuro
        raise PipelineError(f"Path mapping non sicuro: {mapping_path}")

    if not mapping_path.exists():
        logger.error(f"❌ File di mapping semantico non trovato: {mapping_path}")
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_path}")

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        logger.info(f"📄 Mapping semantico caricato da {mapping_path}")
    except Exception as e:
        logger.error(f"❌ Errore lettura/parsing mapping {mapping_path}: {e}")
        raise PipelineError(f"Errore lettura mapping: {e}")

    # ✅ validazione schema + fallback
    if not _validate_mapping_schema(mapping):
        logger.warning(f"⚠️ Mapping semantico vuoto o non valido, caricamento fallback...")
        default_path = Path("config/default_semantic_mapping.yaml")
        if default_path.exists():
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    mapping = yaml.safe_load(f) or {}
                logger.info(f"📄 Mapping di fallback caricato da {default_path}")
            except Exception as e:
                logger.error(f"❌ Errore caricamento mapping di fallback: {e}")
                raise PipelineError(f"Errore caricamento mapping di fallback: {e}")
        else:
            logger.error("❌ Mapping di fallback non trovato, impossibile continuare.")
            raise PipelineError("Mapping di fallback mancante.")

    return mapping
