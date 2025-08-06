"""
Modulo di enrichment semantico: arricchisce i file markdown usando il mapping YAML.
"""

from pathlib import Path
import yaml

from pipeline.logging_utils import get_structured_logger
from semantic.semantic_mapping import load_semantic_mapping  # ✅ Import centralizzato

logger = get_structured_logger("semantic_extractor", "logs/semantic_extractor.log")

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
    - Inserisce sempre lo slug (obbligatorio)
    - Serializza header YAML in modo robusto
    - Logga e non arricchisce se frontmatter già presente
    """
    fname = md_file.name
    semantic_info = mapping.get(fname, {})

    if not semantic_info:
        logger.info(f"Nessun enrichment per {fname}")
        return

    # Obbligo presenza slug
    slug = semantic_info.get("slug")
    if not slug:
        logger.error(f"❌ slug mancante nel mapping per il file {fname} (enrichment saltato)")
        return

    # Costruisci frontmatter YAML con tutti i campi (slug sempre incluso)
    header_dict = dict(semantic_info)  # copia, non muta mapping
    # Assicurati che slug sia presente (già fatto sopra)
    # Eventuali campi aggiuntivi (categorie, tags, ecc.) sono inclusi
    try:
        header_yaml = "---\n" + yaml.safe_dump(header_dict, sort_keys=False, allow_unicode=True) + "---\n\n"
    except Exception as e:
        logger.error(f"❌ Errore serializzazione YAML frontmatter per {fname}: {e}")
        return

    # Leggi il contenuto attuale
    with open(md_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Evita doppio enrichment: non sovrascrivere se frontmatter già presente
    if content.lstrip().startswith("---"):
        logger.info(f"Frontmatter già presente per {fname}, enrichment saltato.")
        return

    # Scrivi header + contenuto
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(header_yaml + content)
    logger.info(f"✅ Enrichment applicato a: {fname} (slug: {slug})")
