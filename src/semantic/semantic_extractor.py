import sys
import os

# 🔄 Adatta il path per esecuzioni dirette fuori package (utile anche in testing/CLI)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pathlib import Path
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import EnrichmentError

from .semantic_mapping import get_semantic_mapping_for_file  # ← import pythonico e pulito

logger = get_structured_logger("semantic.semantic_extractor")

def enrich_markdown_folder(output_folder: str, slug: str = None) -> int:
    """
    Enrichment semantico dei file markdown nella cartella output_folder.
    Attenzione: non genera né README.md né SUMMARY.md (sono generati dalla pipeline principale).
    Aggiunge 'enriched: true' nel frontmatter dei markdown.
    Ritorna il numero di markdown arricchiti.
    Solleva EnrichmentError se la cartella non esiste o in caso di errore bloccante.
    """
    output_dir = Path(output_folder)
    if not output_dir.exists():
        logger.error(f"❌ Cartella output non trovata: {output_folder}")
        raise EnrichmentError(f"Cartella output non trovata: {output_folder}")

    md_files = [f for f in output_dir.glob("*.md") if f.name.lower() not in ("readme.md", "summary.md")]
    logger.info(f"🧠 Enrichment di {len(md_files)} file markdown in {output_folder}...")

    enriched = 0
    for md_path in md_files:
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
            if content.startswith("---"):
                lines = content.split("\n")
                idx = lines.index("---", 1)
                frontmatter = lines[1:idx]
                # Solo se non già arricchito
                if not any(line.startswith("enriched:") for line in frontmatter):
                    frontmatter.append("enriched: true")
                enriched_content = (
                    "---\n" + "\n".join(frontmatter) + "\n---\n" + "\n".join(lines[idx + 1:])
                )
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(enriched_content)
                enriched += 1
                logger.info(f"✅ Enriched: {md_path.name}")
            else:
                logger.warning(f"⚠️ Nessun frontmatter trovato in {md_path.name}. Skippato.")
        except Exception as e:
            logger.error(f"❌ Errore durante enrichment di {md_path.name}: {e}")
            # Soft fail: la pipeline continua sugli altri file

    logger.info(f"Enrichment completato: {enriched}/{len(md_files)} file arricchiti.")
    return enriched

if __name__ == "__main__":
    # Permette uso sia come modulo sia da CLI
    if len(sys.argv) > 1:
        out_folder = sys.argv[1]
    else:
        out_folder = input("Cartella output cliente: ").strip()
    enrich_markdown_folder(out_folder)
