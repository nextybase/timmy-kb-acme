# src/semantic/semantic_extractor.py

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pathlib import Path
import importlib.util
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("semantic.semantic_extractor")

# Import dinamico semantic_mapping.py (nessuna modifica)
mapping_path = os.path.join(os.path.dirname(__file__), "semantic_mapping.py")
spec = importlib.util.spec_from_file_location("semantic_mapping", mapping_path)
semantic_mapping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(semantic_mapping)
get_semantic_mapping_for_file = semantic_mapping.get_semantic_mapping_for_file

# Import dinamico content_utils.py (aggiornato!)
content_utils_path = os.path.join(os.path.dirname(__file__), "..", "pipeline", "content_utils.py")
spec2 = importlib.util.spec_from_file_location("content_utils", content_utils_path)
content_utils = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(content_utils)

def cleanup_top_level_markdown(folder_path: str) -> int:
    """
    Cancella tutti i file .md (inclusi README.md e SUMMARY.md) nella cartella principale.
    Ritorna il numero di file cancellati.
    """
    folder = Path(folder_path)
    removed = 0
    for p in folder.glob("*.md"):
        try:
            p.unlink()
            logger.info(f"🗑️  Cancellato: {p.name}")
            removed += 1
        except Exception as e:
            logger.warning(f"⚠️  Impossibile cancellare {p.name}: {e}")
    if removed == 0:
        logger.info("Nessun file .md trovato da cancellare.")
    return removed

def convert_pdf_to_enriched_markdown(pdf_path: Path, output_path: Path, sem_info: dict) -> bool:
    """
    Crea un markdown arricchito a partire dal nome del PDF e dal mapping semantico fornito.
    """
    try:
        md_name = pdf_path.stem.replace(" ", "_") + ".md"
        md_path = output_path / md_name
        content = f"# Contenuto fittizio per {pdf_path.name}\n"
        fm_lines = [
            "---",
            f"ambito: \"{sem_info.get('ambito', 'unknown')}\"",
            f'descrizione: "{sem_info.get("descrizione", "")}"',
            "---\n"
        ]
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(fm_lines) + content)
        logger.info(f"✅ {md_path} creato e arricchito.")
        return True
    except Exception as e:
        logger.error(f"❌ Errore durante la creazione markdown arricchito: {e}")
        return False

def enrich_pdf_folder_to_markdown(raw_folder: Path, output_folder: Path) -> int:
    """
    Converte e arricchisce tutti i PDF nella cartella raw_folder e li scrive in output_folder.
    Ritorna il numero di file processati.
    """
    raw_dir = Path(raw_folder)
    output_dir = Path(output_folder)
    pdf_files = list(raw_dir.rglob("*.pdf"))
    logger.info(f"🧠 Conversione e enrichment di {len(pdf_files)} PDF...")
    enriched = 0
    for pdf in pdf_files:
        # Ricava la cartella semantica (primo sottofolder dopo /raw)
        parts = pdf.relative_to(raw_dir).parts
        folder = parts[0] if len(parts) > 1 else ""
        sem_info = get_semantic_mapping_for_file(folder)
        if convert_pdf_to_enriched_markdown(pdf, output_dir, sem_info):
            enriched += 1
    logger.info(f"Enrichment completato: {enriched}/{len(pdf_files)} PDF.")
    return enriched

def regenerate_summary_and_readme(output_folder: str, slug: str) -> bool:
    """
    Rigenera SUMMARY.md e README.md nella cartella output_folder per il cliente slug.
    Restituisce True se entrambi i file sono stati creati.
    """
    output_dir = Path(output_folder)
    md_files = [f.name for f in output_dir.glob("*.md") if f.suffix == ".md"]
    success_summary = content_utils.generate_summary_markdown(md_files, str(output_dir))
    success_readme = content_utils.generate_readme_markdown(str(output_dir), slug)
    if success_summary and success_readme:
        logger.info("📑 SUMMARY.md e README.md rigenerati.")
        return True
    logger.error("❌ Errore nella rigenerazione di SUMMARY.md o README.md.")
    return False

def enrich_markdown_folder(output_folder: str, slug: str = None) -> int:
    """
    Effettua enrichment semantico di tutti i PDF in output_folder/raw,
    poi rigenera README.md e SUMMARY.md.
    Ritorna il numero di PDF arricchiti.
    """
    raw_folder = Path(output_folder) / "raw"
    enriched = enrich_pdf_folder_to_markdown(raw_folder, output_folder)
    if slug is not None:
        regenerate_summary_and_readme(output_folder, slug)
    return enriched

if __name__ == "__main__":
    if len(sys.argv) > 2:
        out_folder = sys.argv[1]
        slug = sys.argv[2]
        raw_folder = Path(out_folder) / "raw"
    else:
        out_folder = input("Cartella output cliente: ").strip()
        slug = input("Slug cliente: ").strip()
        raw_folder = Path(out_folder) / "raw"

    choice = input("Vuoi cancellare i file .md nella cartella principale (inclusi README.md e SUMMARY.md)? [y/N] ").strip().lower()
    if choice == "y":
        cleanup_top_level_markdown(out_folder)

    enrich_pdf_folder_to_markdown(raw_folder, out_folder)
    regenerate_summary_and_readme(out_folder, slug)
