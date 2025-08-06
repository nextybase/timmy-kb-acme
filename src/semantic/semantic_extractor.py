"""
Modulo di enrichment semantico: arricchisce i file markdown usando il mapping YAML.
"""

from pathlib import Path
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import settings  # <--- Import centrale settings
from semantic.semantic_mapping import load_semantic_mapping

logger = get_structured_logger("semantic_extractor", str(settings.logs_path))

def enrich_markdown_folder(md_output_path: Path = None, mapping_path: str = "config/semantic_mapping.yaml"):
    """
    Arricchisce tutti i file markdown in una cartella con tag semantici dal mapping YAML.
    Di default usa settings.md_output_path e settings.slug.
    """
    if md_output_path is None:
        md_output_path = settings.md_output_path
    mapping = load_semantic_mapping(mapping_path)
    for md_file in Path(md_output_path).glob("*.md"):
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

    # Forza la presenza dello slug centrale (anche se mancante nel mapping)
    slug = semantic_info.get("slug") or settings.slug
    if not slug:
        logger.error(f"❌ slug mancante sia nel mapping che in settings per il file {fname} (enrichment saltato)")
        return

    header_dict = dict(semantic_info)
    header_dict["slug"] = slug

    try:
        header_yaml = "---\n" + yaml.safe_dump(header_dict, sort_keys=False, allow_unicode=True) + "---\n\n"
    except Exception as e:
        logger.error(f"❌ Errore serializzazione YAML frontmatter per {fname}: {e}")
        return

    with open(md_file, "r", encoding="utf-8") as f:
        content = f.read()

    if content.lstrip().startswith("---"):
        logger.info(f"Frontmatter già presente per {fname}, enrichment saltato.")
        return

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(header_yaml + content)
    logger.info(f"✅ Enrichment applicato a: {fname} (slug: {slug})")
