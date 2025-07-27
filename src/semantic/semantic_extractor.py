"""
Modulo di enrichment semantico: arricchisce i file markdown usando il mapping YAML.
"""

from pathlib import Path
import yaml
import logging

logger = logging.getLogger("semantic_extractor")

def enrich_markdown_folder(md_output_path: str, slug: str, mapping_path: str = "config/semantic_mapping.yaml"):
    """
    Arricchisce tutti i file markdown in una cartella con tag semantici dal mapping YAML.
    """
    mapping = load_semantic_mapping(mapping_path)
    md_folder = Path(md_output_path)
    for md_file in md_folder.glob("*.md"):
        enrich_markdown_file(md_file, mapping)

def enrich_markdown_file(md_file: Path, mapping: dict):
    """
    Applica enrichment semantico a un singolo file markdown, aggiungendo header/categorie dal mapping.
    """
    fname = md_file.name
    semantic_info = mapping.get(fname, {})
    if not semantic_info:
        logger.info(f"Nessun enrichment per {fname}")
        return

    with open(md_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Esempio: aggiungi un header con le categorie (personalizza come vuoi)
    categories = semantic_info.get("categorie", [])
    header = ""
    if categories:
        header += "---\n"
        header += f"categorie: {categories}\n"
        header += "---\n\n"

    # Scrivi il file arricchito solo se manca l'enrichment
    if not content.lstrip().startswith("---"):
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(header + content)
        logger.info(f"Enrichment applicato a: {fname}")

def load_semantic_mapping(mapping_path: str) -> dict:
    mapping_file = Path(mapping_path)
    if not mapping_file.exists():
        logger.warning(f"Mapping non trovato: {mapping_path}")
        return {}
    with open(mapping_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
