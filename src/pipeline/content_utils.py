# src/pipeline/content_utils.py

import logging
from pathlib import Path
import os

logger = logging.getLogger("pipeline.content_utils")

def convert_pdfs_to_markdown_placeholder(config: dict) -> int:
    """
    Simula la conversione di PDF in file Markdown (placeholder).
    Conta e converte tutti i PDF trovati in config["raw_dir"] in file markdown nella cartella di output.
    Ritorna il numero di PDF convertiti.
    """
    raw_path = Path(config["raw_dir"])
    slug = config["slug"]
    output_base = config.get("OUTPUT_DIR_TEMPLATE", "output/timmy-kb-{slug}")
    output_path = Path(output_base.format(slug=slug))
    config["md_output_path"] = str(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    pdf_files = list(raw_path.rglob("*.pdf"))
    logger.info(f"Trovati {len(pdf_files)} PDF da convertire in {raw_path}")

    converted = 0
    for pdf in pdf_files:
        try:
            md_file = output_path / (pdf.stem.replace(" ", "_") + ".md")
            md_file.write_text(f"# Contenuto fittizio per {pdf.name}", encoding="utf-8")
            converted += 1
            logger.debug(f"Creato markdown placeholder per: {pdf.name}")
        except Exception as e:
            logger.warning(f"❌ Errore durante la conversione di {pdf.name}: {e}")

    logger.info(f"Conversione completata: {converted}/{len(pdf_files)} riusciti")
    return converted

def generate_summary_markdown(markdown_files, output_path) -> bool:
    """
    Genera il file SUMMARY.md dai markdown presenti nella cartella output_path.
    Restituisce True se la generazione va a buon fine, False altrimenti.
    """
    summary_md_path = os.path.join(output_path, "SUMMARY.md")
    try:
        with open(summary_md_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Sommario\n\n")
            f.write("* [Introduzione](README.md)\n")
            for file in sorted(markdown_files):
                if file.lower() in {"readme.md", "summary.md"}:
                    continue
                title = os.path.splitext(os.path.basename(file))[0].replace("_", " ")
                f.write(f"* [{title}]({file})\n")

        logger.info(f"📄 SUMMARY.md generato con {len(markdown_files)} file.")
        return True
    except Exception as e:
        logger.error(f"❌ Errore nella generazione di SUMMARY.md: {e}")
        return False

def generate_readme_markdown(output_path, slug) -> bool:
    """
    Genera un file README.md minimale nella cartella output_path per il cliente specificato da slug.
    Restituisce True se la generazione va a buon fine, False altrimenti.
    """
    readme_path = os.path.join(output_path, "README.md")
    try:
        with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# Timmy KB – {slug}\n\n")
            f.write("Benvenuto nella Knowledge Base del cliente **{0}**.\n\n".format(slug))
            f.write("Questa documentazione è generata automaticamente a partire dai PDF forniti durante l’onboarding.\n")

        logger.info("✅ README.md generato con contenuto minimale.")
        return True
    except Exception as e:
        logger.error(f"❌ Errore nella generazione di README.md: {e}")
        return False
