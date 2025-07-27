from pathlib import Path
import os
import datetime

from pipeline.file2md_utils import convert_pdfs_to_markdown
from pipeline.exceptions import ConversionError
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.content_utils")

def convert_files_to_structured_markdown(config: dict, mapping: dict = None) -> int:
    """
    Wrapper per la conversione PDF→Markdown strutturata.
    Garantisce che l'output vada nella cartella corretta secondo config["md_output_path"].
    Ritorna il numero di file convertiti.
    """
    raw_path = Path(config["raw_dir"])
    output_path = Path(config["md_output_path"])  # patch: forzatura definitiva verso /book
    output_path.mkdir(parents=True, exist_ok=True)

    return convert_pdfs_to_markdown(
        pdf_root=raw_path,
        md_output_path=output_path,
        mapping=mapping,
        config=config
    )

def generate_summary_markdown(markdown_files, output_path: str) -> None:
    """
    Genera il file SUMMARY.md dai file Markdown presenti nella cartella output_path.
    Solleva ConversionError in caso di errore.
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
    except Exception as e:
        logger.error(f"❌ Errore nella generazione di SUMMARY.md: {e}")
        raise ConversionError(f"Errore nella generazione di SUMMARY.md: {e}")

def generate_readme_markdown(output_path: str, slug: str) -> None:
    """
    Genera un file README.md minimale nella cartella output_path per il cliente specificato da slug.
    Solleva ConversionError in caso di errore.
    """
    readme_path = os.path.join(output_path, "README.md")
    try:
        with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# Timmy KB – {slug}\n\n")
            f.write(f"Benvenuto nella Knowledge Base del cliente **{slug}**.\n\n")
            f.write("Questa documentazione è generata automaticamente a partire dai file forniti durante l’onboarding.\n")
        logger.info("✅ README.md generato con contenuto minimale.")
    except Exception as e:
        logger.error(f"❌ Errore nella generazione di README.md: {e}")
        raise ConversionError(f"Errore nella generazione di README.md: {e}")
