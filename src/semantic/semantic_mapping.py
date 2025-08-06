"""
Gestione del mapping semantico tra file markdown e le categorie definite (YAML).
Fornisce utility per caricare e applicare il mapping.
"""

import yaml
from pathlib import Path
from pipeline.config_utils import settings  # Import settings per default robusto

def load_semantic_mapping(mapping_path: str = None) -> dict:
    """
    Carica il mapping semantico dal file YAML specificato.
    Ritorna un dizionario: {nome_file_md: {slug, categorie, ...}, ...}
    Usa per default il path centrale da settings.
    """
    if mapping_path is None:
        mapping_path = "config/semantic_mapping.yaml"
    mapping_file = Path(mapping_path)
    if not mapping_file.exists():
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_path}")
    with open(mapping_file, "r", encoding="utf-8") as f:
        mapping = yaml.safe_load(f) or {}
    return mapping

def get_semantic_mapping_for_file(file_path: str, mapping: dict) -> dict:
    """
    Restituisce il mapping semantico (categorie, slug, ecc.) per un file markdown specifico.
    Args:
        file_path (str): Path del file markdown (usa solo il nome).
        mapping (dict): Mapping completo caricato da YAML.
    Returns:
        dict: Dizionario con info semantiche (vuoto se non trovate).
    """
    fname = Path(file_path).name
    return mapping.get(fname, {})

def list_semantic_categories(mapping: dict) -> list:
    """
    Restituisce la lista unica delle categorie semantiche definite nel mapping.
    """
    return list({cat for m in mapping.values() for cat in m.get("categorie", [])})

def check_missing_slugs(mapping: dict) -> list:
    """
    Restituisce la lista dei file nel mapping che NON hanno uno slug.
    Utile per validare la completezza prima dell'enrichment.
    """
    return [fname for fname, m in mapping.items() if not m.get("slug")]
