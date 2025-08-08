"""
Gestione del mapping semantico tra file markdown e le categorie definite (YAML).
Fornisce utility per caricare e applicare il mapping.
"""

import yaml
import shutil
from pathlib import Path
from pipeline.config_utils import get_settings_for_slug
from pipeline.logging_utils import get_structured_logger
from pipeline.constants import BACKUP_SUFFIX
from pipeline.exceptions import SemanticMappingError

logger = get_structured_logger("semantic.semantic_mapping")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings.
    Se non viene passato esplicitamente, usa get_settings_for_slug().
    """
    if settings is None:
        return get_settings_for_slug()
    return settings


def load_semantic_mapping(mapping_path: str = None, settings=None) -> dict:
    """
    Carica il mapping semantico dal file YAML specificato.
    Ritorna un dizionario: {nome_file_md: {slug, categoria, ...}, ...}
    """
    settings = _resolve_settings(settings)

    if mapping_path is None:
        mapping_path = settings.base_dir / "config" / "semantic_mapping.yaml"

    mapping_file = Path(mapping_path)
    if not mapping_file.exists():
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_file}")

    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        logger.info(f"✅ Mapping semantico caricato da {mapping_file}")
        return mapping
    except Exception as e:
        logger.error(f"❌ Errore caricando mapping da {mapping_file}: {e}")
        raise SemanticMappingError(f"Errore lettura mapping: {e}") from e


def save_semantic_mapping(mapping: dict, mapping_path: str = None, settings=None):
    """
    Salva il mapping semantico su file YAML in modo sicuro.
    Crea un backup prima di sovrascrivere.
    """
    settings = _resolve_settings(settings)

    if mapping_path is None:
        mapping_path = settings.base_dir / "config" / "semantic_mapping.yaml"

    mapping_file = Path(mapping_path)

    if mapping_file.exists():
        backup_path = mapping_file.with_suffix(BACKUP_SUFFIX)
        shutil.copy(mapping_file, backup_path)
        logger.info(f"💾 Backup mapping in {backup_path}")

    try:
        with open(mapping_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(mapping, f, allow_unicode=True)
        logger.info(f"✅ Mapping semantico salvato in {mapping_file}")
    except Exception as e:
        logger.error(f"❌ Errore salvando mapping in {mapping_file}: {e}")
        raise SemanticMappingError(f"Errore salvataggio mapping: {e}") from e


def get_semantic_mapping_for_file(file_path: str, mapping: dict) -> dict:
    """
    Restituisce il mapping semantico (categoria, slug, ecc.) per un file markdown specifico.
    """
    fname = Path(file_path).name
    return mapping.get(fname, {})


def list_semantic_categories(mapping: dict) -> list:
    """
    Restituisce la lista unica delle categorie semantiche definite nel mapping.
    """
    return list({cat for m in mapping.values() for cat in m.get("categoria", [])})


def check_missing_slugs(mapping: dict) -> list:
    """
    Restituisce la lista dei file nel mapping che NON hanno uno slug.
    Utile per validare la completezza prima dell'enrichment.
    """
    return [fname for fname, m in mapping.items() if not m.get("slug")]
