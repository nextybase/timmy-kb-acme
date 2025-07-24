from pathlib import Path
import os
import datetime

from pipeline.file2md_utils import extract_file_to_markdown, load_tags_by_category
from pipeline.exceptions import ConversionError
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.content_utils")

def convert_files_to_structured_markdown(config: dict, mapping: dict = None) -> int:
    """
    Converte tutti i file supportati (inizialmente solo PDF) trovati in config["raw_dir"]
    in file Markdown nella cartella di output, aggiungendo tag di paragrafo e frontmatter ricco.
    Ogni markdown ha: titolo, categoria, cartella origine, data conversione, stato normalizzazione.
    Ritorna il numero di file convertiti.
    Solleva ConversionError se la conversione globale fallisce.
    """
    raw_path = Path(config["raw_dir"])
    slug = config["slug"]
    output_path = Path(config.get("md_output_path", f"output/timmy-kb-{slug}/book"))
    output_path.mkdir(parents=True, exist_ok=True)

    # Solo PDF (espandibile in futuro)
    files = [f for f in raw_path.rglob("*") if f.is_file() and f.suffix.lower() in {".pdf"}]

    logger.info(f"🟢 Trovati {len(files)} file da convertire in {raw_path}")

    def get_categoria_from_path(file_path):
        folder = file_path.parent.name.lower()
        if mapping and folder in mapping:
            return mapping[folder]
        return folder

    tags_by_cat = load_tags_by_category()

    converted = 0
    for file in files:
        try:
            titolo = file.stem.replace("_", " ").title()
            categoria = get_categoria_from_path(file)
            frontmatter = {
                "titolo": titolo,
                "categoria": categoria,
                "origine_cartella": file.parent.name,
                "data_conversione": datetime.date.today().isoformat(),
                "stato_normalizzazione": "completato"
            }
            extract_file_to_markdown(file, output_path, frontmatter, tags_by_cat=tags_by_cat)
            converted += 1
            logger.info(f"✅ Markdown creato per: {file.name}")
        except Exception as e:
            logger.error(f"❌ Errore durante la conversione di {file.name}: {e}")
            raise ConversionError(f"Errore durante la conversione di {file.name}: {e}")

    logger.info(f"🏁 Conversione completata: {converted}/{len(files)} riusciti")
    return converted

def generate_summary_markdown(markdown_files, output_path) -> None:
    """
    Genera il file SUMMARY.md dai markdown presenti nella cartella output_path.
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

def generate_readme_markdown(output_path, slug) -> None:
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
