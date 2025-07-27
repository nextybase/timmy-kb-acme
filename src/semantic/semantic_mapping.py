"""
Gestione del mapping semantico tra file markdown e le categorie definite (YAML).
Fornisce utilità per caricare e applicare il mapping.
"""
import yaml
from pathlib import Path

def load_semantic_mapping(mapping_path: str = "config/semantic_mapping.yaml") -> dict:
    """
    Carica il mapping semantico dal file YAML specificato.
    """
    mapping_file = Path(mapping_path)
    if not mapping_file.exists():
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_path}")
    with open(mapping_file, "r", encoding="utf-8") as f:
        mapping = yaml.safe_load(f)
    return mapping

def get_semantic_mapping_for_file(file_path: str, mapping: dict) -> dict:
    """
    Trova la categoria semantica per un file markdown specifico.
    """
    fname = Path(file_path).name
    return mapping.get(fname, {})

# Se servono funzioni aggiuntive (esempio di utility):
def list_semantic_categories(mapping: dict) -> list:
    """
    Restituisce la lista delle categorie semantiche definite.
    """
    return list({cat for m in mapping.values() for cat in m.get("categories", [])})
