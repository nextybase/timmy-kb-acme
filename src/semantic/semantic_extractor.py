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

def enrich_markdown_folder(output_folder: str, slug: str = None) -> int:
    """
    Enrichment semantico dei file markdown nella cartella output_folder.
    Attenzione: non genera né README.md né SUMMARY.md (ora spostati nella pipeline).
    Ritorna il numero di markdown arricchiti.
    """
    output_dir = Path(output_folder)
    md_files = [f for f in output_dir.glob("*.md") if f.name.lower() not in ("readme.md", "summary.md")]
    logger.info(f"🧠 Enrichment di {len(md_files)} file markdown in {output_folder}...")

    enriched = 0
    for md_path in md_files:
        try:
            # Leggi markdown esistente
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Esempio enrichment: aggiungi "enriched: true" al frontmatter se presente
            if content.startswith("---"):
                lines = content.split("\n")
                idx = lines.index("---", 1)  # seconda chiusura frontmatter
                frontmatter = lines[1:idx]
                # Arricchisci i metadati (qui esemplare, si può espandere)
                if not any(line.startswith("enriched:") for line in frontmatter):
                    frontmatter.append("enriched: true")
                # Riscrivi il markdown arricchito
                enriched_content = (
                    "---\n" + "\n".join(frontmatter) + "\n---\n" + "\n".join(lines[idx+1:])
                )
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(enriched_content)
                enriched += 1
                logger.info(f"✅ Enriched: {md_path.name}")
            else:
                logger.warning(f"⚠️ Nessun frontmatter trovato in {md_path.name}. Skippato.")
        except Exception as e:
            logger.error(f"❌ Errore durante enrichment di {md_path.name}: {e}")
    logger.info(f"Enrichment completato: {enriched}/{len(md_files)} file arricchiti.")
    return enriched

if __name__ == "__main__":
    if len(sys.argv) > 1:
        out_folder = sys.argv[1]
    else:
        out_folder = input("Cartella output cliente: ").strip()
    enrich_markdown_folder(out_folder)
