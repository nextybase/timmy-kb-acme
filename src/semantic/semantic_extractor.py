"""
Modulo per l'estrazione e l'arricchimento semantico dei documenti markdown
nella pipeline Timmy-KB.

Refactor v1.0:
- Uso esclusivo di ClientContext
- Eliminato get_settings_for_slug
- Path e config derivati da context
"""

from pathlib import Path
from typing import Optional, List, Dict
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError, FileNotFoundError, NotADirectoryError
from pipeline.constants import CONFIG_FILE_NAME, SEMANTIC_MAPPING_FILE
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath
from semantic.semantic_mapping import load_semantic_mapping


def _list_markdown_files(context: ClientContext, logger=None) -> List[Path]:
    """Ritorna la lista ordinata dei file markdown nella directory md_dir del contesto."""
    logger = logger or get_structured_logger("semantic.files", context=context)
    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PipelineError(f"Path non sicuro: {context.md_dir}", slug=context.slug, file_path=context.md_dir)

    if not context.md_dir.exists():
        raise FileNotFoundError(f"Directory markdown non trovata: {context.md_dir}")
    if not context.md_dir.is_dir():
        raise NotADirectoryError(f"Il path non è una directory: {context.md_dir}")

    files = sorted(context.md_dir.glob("*.md"))
    logger.info(f"📄 Trovati {len(files)} file markdown in {context.md_dir}", extra={"slug": context.slug})
    return files


def extract_semantic_concepts(context: ClientContext, logger=None) -> Dict:
    """Estrae i concetti semantici dai file markdown basandosi sul mapping in config/."""
    logger = logger or get_structured_logger("semantic.extract", context=context)

    mapping = load_semantic_mapping(context, logger=logger)
    markdown_files = _list_markdown_files(context, logger=logger)

    extracted_data = {}
    for concept, keywords in mapping.items():
        matches = []
        for file in markdown_files:
            try:
                content = file.read_text(encoding="utf-8")
                for kw in keywords:
                    if kw.lower() in content.lower():
                        matches.append({"file": file.name, "keyword": kw})
            except Exception as e:
                logger.warning(f"⚠️ Impossibile leggere {file}: {e}", extra={"slug": context.slug, "file_path": file})
                continue
        extracted_data[concept] = matches

    logger.info(f"🔍 Estrazione concetti completata per {context.slug}", extra={"slug": context.slug})
    return extracted_data


def enrich_markdown_folder(context: ClientContext, logger=None) -> None:
    """Orchestratore dell'arricchimento semantico."""
    logger = logger or get_structured_logger("semantic.enrich", context=context)

    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PipelineError(f"Path non sicuro: {context.md_dir}", slug=context.slug, file_path=context.md_dir)

    if not context.md_dir.exists():
        raise FileNotFoundError(f"Directory markdown non trovata: {context.md_dir}")

    markdown_files = _list_markdown_files(context, logger=logger)
    logger.info(f"📂 Avvio arricchimento semantico su {len(markdown_files)} file", extra={"slug": context.slug})

    for file in markdown_files:
        try:
            logger.debug(f"✏️ Elaborazione semantica per {file.name}", extra={"slug": context.slug, "file_path": file})
            # Qui avverrebbe l'arricchimento effettivo
        except Exception as e:
            logger.warning(f"⚠️ Errore durante arricchimento {file}: {e}", extra={"slug": context.slug, "file_path": file})
            continue

    logger.info("✅ Arricchimento semantico completato.", extra={"slug": context.slug})
