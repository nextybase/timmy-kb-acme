# src/semantic/semantic_extractor.py
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
from pipeline.config_utils import _validate_path_in_base_dir
from pipeline.exceptions import PipelineError
from pipeline.constants import CONFIG_FILE_NAME, SEMANTIC_MAPPING_FILE
from pipeline.context import ClientContext

# ---------------------------
# Utility interne
# ---------------------------
def _load_semantic_mapping(context: ClientContext, logger=None) -> dict:
    """Carica il file di mapping semantico YAML dal contesto."""
    logger = logger or get_structured_logger("semantic.mapping", context=context)
    mapping_path = context.config_dir / SEMANTIC_MAPPING_FILE

    _validate_path_in_base_dir(mapping_path, context.base_dir)
    if not mapping_path.exists():
        logger.error(f"❌ File di mapping semantico non trovato: {mapping_path}")
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_path}")

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        logger.info(f"📄 Mapping semantico caricato da {mapping_path}")
        return mapping
    except Exception as e:
        logger.error(f"❌ Errore lettura/parsing mapping {mapping_path}: {e}")
        raise PipelineError(f"Errore lettura mapping: {e}")

def _list_markdown_files(context: ClientContext, logger=None) -> List[Path]:
    """Ritorna la lista ordinata dei file markdown nella directory md_dir del contesto."""
    logger = logger or get_structured_logger("semantic.files", context=context)
    _validate_path_in_base_dir(context.md_dir, context.base_dir)

    if not context.md_dir.exists():
        raise FileNotFoundError(f"Directory markdown non trovata: {context.md_dir}")
    if not context.md_dir.is_dir():
        raise NotADirectoryError(f"Il path non è una directory: {context.md_dir}")

    files = sorted(context.md_dir.glob("*.md"))
    logger.info(f"📄 Trovati {len(files)} file markdown in {context.md_dir}")
    return files

# ---------------------------
# Estrazione concetti semantici
# ---------------------------
def extract_semantic_concepts(context: ClientContext, logger=None) -> dict:
    """
    Estrae i concetti semantici dai file markdown basandosi sul mapping definito in config/.
    """
    logger = logger or get_structured_logger("semantic.extract", context=context)

    mapping = _load_semantic_mapping(context, logger=logger)
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
                logger.warning(f"⚠️ Impossibile leggere {file}: {e}")
        extracted_data[concept] = matches

    logger.info(f"✅ Estrazione concetti completata per cliente {context.slug}")
    return extracted_data

# ---------------------------
# Orchestratore arricchimento semantico (placeholder)
# ---------------------------
def enrich_markdown_folder(context: ClientContext, logger=None):
    """
    Orchestratore dell'arricchimento semantico.
    """
    logger = logger or get_structured_logger("semantic.enrich", context=context)
    _validate_path_in_base_dir(context.md_dir, context.base_dir)

    if not context.md_dir.exists():
        raise FileNotFoundError(f"Directory markdown non trovata: {context.md_dir}")

    markdown_files = _list_markdown_files(context, logger=logger)
    logger.info(f"📌 Avvio arricchimento semantico su {len(markdown_files)} file in {context.md_dir}")

    # Placeholder logica arricchimento
    for file in markdown_files:
        logger.debug(f"📄 Elaborazione semantica per {file.name}")

    logger.info("✨ Arricchimento semantico completato.")

# ---------------------------
# CLI
# ---------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Estrazione e arricchimento semantico da markdown Timmy-KB")
    parser.add_argument("--slug", type=str, required=True, help="Slug cliente (es: acme-srl)")
    args = parser.parse_args()

    try:
        context = ClientContext.load(args.slug)
        results = extract_semantic_concepts(context)
        get_structured_logger("semantic.cli", context=context).info(f"📊 Risultati estrazione: {results}")
    except Exception as e:
        get_structured_logger("semantic.cli").error(f"❌ Errore: {e}")
