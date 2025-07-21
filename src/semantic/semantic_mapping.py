# src/semantic/semantic_mapping.py

import yaml
from pathlib import Path
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("semantic.semantic_mapping")

# Path al file di mapping semantico (relativo alla root progetto)
SEMANTIC_YAML_PATH = Path("config/cartelle_semantica.yaml")

def load_semantic_mapping() -> dict:
    """
    Carica il file YAML della struttura semantica delle cartelle.
    Restituisce il mapping completo come dizionario.
    """
    try:
        with open(SEMANTIC_YAML_PATH, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f)
        logger.info(f"✅ Mapping semantico caricato da {SEMANTIC_YAML_PATH}")
        return mapping
    except Exception as e:
        logger.error(f"❌ Errore nel caricamento mapping semantico: {e}")
        return {}

def get_semantic_mapping_for_folder(folder_name: str) -> dict:
    """
    Dato il nome di una cartella (es: 'glossario'), restituisce il mapping semantico.
    """
    mapping = load_semantic_mapping()
    info = mapping.get(folder_name)
    if info:
        logger.debug(f"Mapping trovato per cartella: {folder_name}")
        return info
    logger.warning(f"Cartella '{folder_name}' non mappata.")
    return {
        "ambito": "unknown",
        "descrizione": "Cartella non mappata",
        "esempio": [],
    }

def get_semantic_mapping_for_file(filepath: str) -> dict:
    """
    Dato un path file (Markdown), cerca la prima cartella tematica nell'albero
    e restituisce il mapping semantico relativo.
    """
    p = Path(filepath)
    for part in p.parts:
        info = get_semantic_mapping_for_folder(part)
        if info["ambito"] != "unknown":
            logger.debug(f"Mapping semantico trovato per file: {filepath} (cartella: {part})")
            return info
    logger.warning(f"Nessuna cartella tematica trovata per file: {filepath}")
    return {
        "ambito": "unknown",
        "descrizione": "File fuori struttura semantica",
        "esempio": [],
    }
