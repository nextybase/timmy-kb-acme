import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def convert_pdfs_to_markdown(config: dict):
    """
    Simula la conversione di PDF in file Markdown.
    Al momento non esegue conversione reale ma rileva la presenza di PDF nella cartella raw.
    """
    raw_path = Path(config["drive_input_path"])
    output_path = Path(config["md_output_path"])

    # Verifica e crea la directory di output se non esiste
    output_path.mkdir(parents=True, exist_ok=True)

    pdf_files = list(raw_path.rglob("*.pdf"))
    logger.info(f"Trovati {len(pdf_files)} PDF da convertire in {raw_path}")

    converted = 0
    for pdf in pdf_files:
        try:
            md_file = output_path / (pdf.stem + ".md")
            md_file.write_text(f"# Contenuto fittizio per {pdf.name}", encoding="utf-8")
            converted += 1
        except Exception as e:
            logger.warning(f"❌ Errore durante la conversione di {pdf.name}: {e}")

    logger.info(f"Conversione completata: {converted}/{len(pdf_files)} riusciti")
