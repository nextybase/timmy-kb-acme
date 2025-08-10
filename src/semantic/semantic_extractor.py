"""
semantic_extractor.py

Modulo per l'estrazione e l'arricchimento semantico dei documenti markdown generati dalla pipeline Timmy-KB.

Struttura attuale:
- Caricamento mapping semantico
- Estrazione concetti
- Orchestratore di arricchimento (placeholder, per sviluppo futuro)

Refactor Fase 2:
- Separazione netta dalla pipeline di costruzione
- Import aggiornati: _validate_path_in_base_dir da config_utils
- Logging uniforme
- Preparazione per estensioni modulari
"""

from pathlib import Path
from typing import Optional, List
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug, _validate_path_in_base_dir
from pipeline.exceptions import PipelineError
from pipeline.constants import CONFIG_FILE_NAME, SEMANTIC_MAPPING_FILE

logger = get_structured_logger("pipeline.semantic_extractor")


# -------------------------------------------------
# Funzioni di utilità
# -------------------------------------------------
def _load_semantic_mapping(mapping_path: Path) -> dict:
    """
    Carica il file di mapping semantico YAML.
    """
    _validate_path_in_base_dir(mapping_path, mapping_path.parent)
    if not mapping_path.exists():
        logger.error(f"❌ File di mapping semantico non trovato: {mapping_path}")
        raise FileNotFoundError(f"File di mapping semantico non trovato: {mapping_path}")

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        logger.info(f"📄 Mapping semantico caricato da {mapping_path}")
        return mapping
    except Exception as e:
        logger.error(f"❌ Errore nella lettura/parsing di {mapping_path}: {e}")
        raise PipelineError(f"Errore lettura mapping: {e}")


def _list_markdown_files(md_dir: Path) -> List[Path]:
    """
    Restituisce la lista ordinata di file markdown nella directory indicata.
    """
    _validate_path_in_base_dir(md_dir, md_dir.parent)
    if not md_dir.exists():
        raise FileNotFoundError(f"Directory markdown non trovata: {md_dir}")
    if not md_dir.is_dir():
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")

    files = sorted(md_dir.glob("*.md"))
    logger.info(f"📄 {len(files)} file markdown trovati in {md_dir}")
    return files


# -------------------------------------------------
# Estrazione concetti semantici
# -------------------------------------------------
def extract_semantic_concepts(slug: Optional[str] = None, md_dir: Optional[Path] = None) -> dict:
    """
    Estrae i concetti semantici dai file markdown in base al mapping definito.

    Args:
        slug: Slug cliente (se non passato, obbligatorio md_dir)
        md_dir: Path alla directory contenente i file markdown

    Returns:
        dict: mapping concetti → contenuti trovati
    """
    if not slug and not md_dir:
        raise PipelineError("Necessario passare uno slug o un path markdown.")

    settings = get_settings_for_slug(slug) if slug else None
    md_path = md_dir or settings.md_output_path

    mapping_path = (
        settings.config_dir / SEMANTIC_MAPPING_FILE
        if settings else md_path.parent / CONFIG_FILE_NAME
    )

    mapping = _load_semantic_mapping(mapping_path)
    markdown_files = _list_markdown_files(md_path)

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

    logger.info(f"✅ Estrazione concetti completata per {slug or md_dir}")
    return extracted_data


# -------------------------------------------------
# Orchestratore arricchimento semantico (placeholder)
# -------------------------------------------------
def enrich_markdown_folder(md_dir: Path, semantic_mapping: dict, logger=None):
    """
    Orchestratore della fase di arricchimento semantico.
    Al momento esegue solo validazioni e logging.
    In futuro:
      - Analisi del contenuto markdown
      - Annotazioni semantiche
      - Aggiornamento dei file
      - Generazione di metadati aggiuntivi
    """
    if logger is None:
        logger = get_structured_logger("semantic.enrich")

    _validate_path_in_base_dir(md_dir, md_dir.parent)
    if not md_dir.exists():
        raise FileNotFoundError(f"Directory markdown non trovata: {md_dir}")

    markdown_files = _list_markdown_files(md_dir)
    logger.info(f"📂 Avvio arricchimento semantico su {len(markdown_files)} file in {md_dir}")

    # Placeholder: in futuro qui ci sarà la pipeline semantica
    for file in markdown_files:
        logger.debug(f"🔍 Analisi placeholder per {file.name}")

    logger.info("✅ Arricchimento semantico completato (placeholder)")


# -------------------------------------------------
# CLI
# -------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Estrazione e arricchimento semantico da markdown Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--md_dir", type=str, help="Percorso directory markdown")
    args = parser.parse_args()

    try:
        if args.slug or args.md_dir:
            extracted = extract_semantic_concepts(
                slug=args.slug,
                md_dir=Path(args.md_dir) if args.md_dir else None
            )
            logger.info(f"📊 Risultati estrazione: {extracted}")
        else:
            logger.error("❌ Necessario passare uno slug o un path markdown.")
    except Exception as e:
        logger.error(f"❌ Errore: {e}")
