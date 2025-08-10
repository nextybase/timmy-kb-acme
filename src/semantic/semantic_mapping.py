"""
semantic_mapping.py

Gestione del mapping semantico tra file markdown e categorie definite (YAML).
Permette di caricare e salvare il mapping in modo sicuro e coerente con la pipeline.

Refactor Fase 2:
- Rimosso _resolve_settings → uso di get_settings_for_slug()
- Import aggiornati: _validate_path_in_base_dir da config_utils
- Uso eccezioni built-in per FileNotFoundError
- Logging uniforme
- Snellita la logica di caricamento e salvataggio
"""

import yaml
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List

from pipeline.config_utils import get_settings_for_slug, _validate_path_in_base_dir
from pipeline.logging_utils import get_structured_logger
from pipeline.constants import BACKUP_SUFFIX, SEMANTIC_MAPPING_FILE
from pipeline.exceptions import SemanticMappingError, PipelineError

logger = get_structured_logger("semantic.semantic_mapping")


def load_semantic_mapping(mapping_path: Optional[Path] = None,
                          slug: Optional[str] = None) -> Dict[str, Any]:
    """
    Carica il mapping semantico da file YAML.

    Args:
        mapping_path: Percorso al file di mapping (opzionale)
        slug: Slug cliente, usato se mapping_path non è passato

    Returns:
        dict: Mapping semantico
    """
    settings = get_settings_for_slug(slug) if slug else None

    if mapping_path is None:
        if not settings:
            raise PipelineError("Necessario passare mapping_path o slug.")
        mapping_path = settings.config_dir / SEMANTIC_MAPPING_FILE

    _validate_path_in_base_dir(mapping_path, mapping_path.parent)

    if not mapping_path.exists():
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_path}")

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        logger.info(f"📄 Mapping semantico caricato da {mapping_path}")
        return mapping
    except Exception as e:
        logger.error(f"❌ Errore caricamento mapping {mapping_path}: {e}")
        raise SemanticMappingError(f"Errore caricamento mapping: {e}")


def save_semantic_mapping(mapping: Dict[str, Any],
                          mapping_path: Optional[Path] = None,
                          slug: Optional[str] = None):
    """
    Salva il mapping semantico su file YAML con backup.

    Args:
        mapping: Dati del mapping da salvare
        mapping_path: Percorso al file di mapping (opzionale)
        slug: Slug cliente, usato se mapping_path non è passato
    """
    settings = get_settings_for_slug(slug) if slug else None

    if mapping_path is None:
        if not settings:
            raise PipelineError("Necessario passare mapping_path o slug.")
        mapping_path = settings.config_dir / SEMANTIC_MAPPING_FILE

    _validate_path_in_base_dir(mapping_path, mapping_path.parent)

    if mapping_path.exists():
        backup_path = mapping_path.with_suffix(BACKUP_SUFFIX)
        shutil.copy(mapping_path, backup_path)
        logger.info(f"📦 Backup mapping creato in {backup_path}")

    try:
        with open(mapping_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(mapping, f, allow_unicode=True)
        logger.info(f"✅ Mapping semantico salvato in {mapping_path}")
    except Exception as e:
        logger.error(f"❌ Errore salvataggio mapping {mapping_path}: {e}")
        raise SemanticMappingError(f"Errore salvataggio mapping: {e}")


def get_semantic_mapping_for_file(file_path: str,
                                  mapping: Dict[str, Any]) -> Dict[str, Any]:
    """
    Restituisce il mapping per un file markdown specifico.

    Args:
        file_path: Nome o path del file markdown
        mapping: Mapping semantico completo

    Returns:
        dict: Categoria/slug associati al file
    """
    fname = Path(file_path).name
    return mapping.get(fname, {})


def list_semantic_categories(mapping: Dict[str, Any]) -> List[str]:
    """
    Restituisce la lista unica di tutte le categorie semantiche nel mapping.
    """
    return list({cat for m in mapping.values() for cat in m.get("categoria", [])})


def check_missing_slugs(mapping: Dict[str, Any]) -> List[str]:
    """
    Restituisce la lista di file nel mapping che non hanno uno slug definito.
    """
    return [fname for fname, m in mapping.items() if not m.get("slug")]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gestione file di mapping semantico Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente")
    parser.add_argument("--list", action="store_true", help="Lista categorie")
    args = parser.parse_args()

    try:
        mapping = load_semantic_mapping(slug=args.slug)
        if args.list:
            print("Categorie:", list_semantic_categories(mapping))
    except Exception as e:
        logger.error(f"❌ Errore: {e}")
