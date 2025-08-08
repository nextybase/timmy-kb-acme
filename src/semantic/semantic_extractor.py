"""
semantic_extractor.py

Modulo per l’arricchimento semantico dei file markdown:
applica intestazioni e categorie ai file markdown usando il mapping YAML fornito.
"""

from pathlib import Path
import yaml
import shutil

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug
from semantic.semantic_mapping import load_semantic_mapping
from pipeline.constants import BACKUP_SUFFIX, SEMANTIC_MAPPING_FILE_NAME
from pipeline.exceptions import EnrichmentError
from pipeline.utils import _validate_path_in_base_dir


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings.
    Se non viene passato esplicitamente, usa get_settings_for_slug().
    """
    return settings or get_settings_for_slug()


def enrich_markdown_folder(
    md_output_path: Path = None,
    mapping_path: str = f"config/{SEMANTIC_MAPPING_FILE_NAME}",
    settings=None
):
    """
    Applica arricchimento semantico a tutti i file markdown in una cartella
    usando il mapping YAML.
    """
    settings = _resolve_settings(settings)
    logger = get_structured_logger("semantic_extractor", str(settings.logs_path))

    if md_output_path is None:
        md_output_path = settings.md_output_path

    _validate_path_in_base_dir(md_output_path, settings.base_dir)

    mapping = load_semantic_mapping(mapping_path)
    for md_file in Path(md_output_path).glob("*.md"):
        enrich_markdown_file(md_file, mapping, settings=settings)


def enrich_markdown_file(md_file: Path, mapping: dict, settings=None):
    """
    Applica arricchimento semantico a un singolo file markdown,
    aggiungendo header/categoria dal mapping.
    """
    settings = _resolve_settings(settings)
    logger = get_structured_logger("semantic_extractor", str(settings.logs_path))

    _validate_path_in_base_dir(md_file, settings.base_dir)

    fname = md_file.name
    semantic_info = mapping.get(fname, {})

    # Recupero slug
    slug = semantic_info.get("slug") or settings.slug
    if not slug:
        logger.error(f"❌ Slug mancante sia nel mapping che in settings per il file {fname}. Enrichment saltato.")
        return

    # Creazione header YAML
    header_dict = dict(semantic_info)
    header_dict["slug"] = slug
    try:
        header_yaml = "---\n" + yaml.safe_dump(header_dict, sort_keys=False, allow_unicode=True) + "---\n\n"
    except Exception as e:
        logger.error(f"❌ Errore serializzando YAML per {fname}: {e}")
        return

    # Backup file prima della modifica
    backup_path = md_file.with_suffix(BACKUP_SUFFIX)
    try:
        shutil.copy(md_file, backup_path)
        logger.info(f"💾 Backup creato: {backup_path}")
    except Exception as e:
        logger.warning(f"⚠️ Impossibile creare backup per {fname}: {e}")

    # Lettura contenuto originale
    try:
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"❌ Errore lettura {fname}: {e}")
        return

    # Evita doppio inserimento header
    if content.strip().startswith("---"):
        logger.info(f"ℹ️ Header già presente in {fname}, enrichment saltato.")
        return

    # Scrittura con header
    try:
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(header_yaml + content)
        logger.info(f"📝 Enrichment applicato a: {fname} (slug: {slug})")
    except Exception as e:
        logger.error(f"❌ Errore scrittura {fname}: {e}")
        try:
            shutil.copy(backup_path, md_file)
            logger.info(f"♻️ Ripristinato file da backup per {fname}")
        except Exception as rollback_err:
            logger.critical(f"❌ Errore nel rollback per {fname}: {rollback_err}")
        raise EnrichmentError(f"Errore enrichment per {fname}") from e
