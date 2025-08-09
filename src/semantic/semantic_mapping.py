"""
semantic_mapping.py

Gestione del mapping semantico tra file markdown e categorie definite (YAML).
Permette di caricare e salvare il mapping in modo sicuro.
"""

import yaml
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List

from pipeline.config_utils import get_settings_for_slug
from pipeline.logging_utils import get_structured_logger
from pipeline.constants import BACKUP_SUFFIX, SEMANTIC_MAPPING_FILE_NAME
from pipeline.exceptions import SemanticMappingError, PipelineError
from pipeline.utils import _validate_path_in_base_dir

logger = get_structured_logger("semantic.semantic_mapping")


def _resolve_settings(settings=None, slug=None):
    """
    Restituisce un'istanza Settings.
    Se non viene passato esplicitamente, usa get_settings_for_slug(slug).
    """
    if settings is not None:
        return settings
    if slug is not None:
        return get_settings_for_slug(slug)
    raise PipelineError("Impossibile risolvere settings: manca 'settings' e 'slug'.")


def load_semantic_mapping(mapping_path: Optional[str] = None, settings=None, slug=None) -> Dict[str, Any]:
    """
    Carica il mapping semantico da file YAML.
    Ritorna un dizionario: {nome_file_md: {slug, categoria, ...}, ...}
    """
    settings = _resolve_settings(settings, slug)

    if mapping_path is None:
        mapping_path = settings.base_dir / "config" / SEMANTIC_MAPPING_FILE_NAME

    mapping_file = Path(mapping_path)
    _validate_path_in_base_dir(mapping_file, settings.base_dir)

    if not mapping_file.exists():
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_file}")

    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        logger.info(f"📥 Mapping semantico caricato da {mapping_file}")
        return mapping
    except Exception as e:
        logger.error(f"❌ Errore caricando mapping da {mapping_file}: {e}")
        raise SemanticMappingError(f"Errore lettura mapping: {e}")


def save_semantic_mapping(mapping: Dict[str, Any], mapping_path: Optional[str] = None, settings=None, slug=None):
    """
    Salva il mapping semantico su file YAML in modo sicuro, con backup.
    """
    settings = _resolve_settings(settings, slug)

    if mapping_path is None:
        mapping_path = settings.base_dir / "config" / SEMANTIC_MAPPING_FILE_NAME

    mapping_file = Path(mapping_path)
    _validate_path_in_base_dir(mapping_file, settings.base_dir)

    if mapping_file.exists():
        backup_path = mapping_file.with_suffix(BACKUP_SUFFIX)
        shutil.copy(mapping_file, backup_path)
        logger.info(f"💾 Backup mapping creato in {backup_path}")

    try:
        with open(mapping_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(mapping, f, allow_unicode=True)
        logger.info(f"📤 Mapping semantico salvato in {mapping_file}")
    except Exception as e:
        logger.error(f"❌ Errore salvando mapping in {mapping_file}: {e}")
        raise SemanticMappingError(f"Errore salvataggio mapping: {e}")


def get_semantic_mapping_for_file(file_path: str, mapping: Dict[str, Any]) -> Dict[str, Any]:
    """
    Restituisce il mapping semantico (categoria, slug, ecc.) per un file markdown specifico.
    """
    fname = Path(file_path).name
    return mapping.get(fname, {})


def list_semantic_categories(mapping: Dict[str, Any]) -> List[str]:
    """
    Restituisce la lista unica delle categorie semantiche definite nel mapping.
    """
    return list({cat for m in mapping.values() for cat in m.get("categoria", [])})


def check_missing_slugs(mapping: Dict[str, Any]) -> List[str]:
    """
    Restituisce la lista dei file nel mapping che NON hanno uno slug definito.
    Utile per validare la completezza prima dell'enrichment.
    """
    return [fname for fname, m in mapping.items() if not m.get("slug")]
