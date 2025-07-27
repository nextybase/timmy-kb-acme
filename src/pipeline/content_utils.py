"""
pipeline/content_utils.py
Utility per la generazione e gestione dei markdown (book), SUMMARY.md, README.md, 
conversioni e post-processing per la pipeline Timmy-KB.
Ogni funzione accetta come path SOLO le property configurate di config_utils.py.
"""

from pathlib import Path
import logging

def convert_files_to_structured_markdown(config, mapping):
    """
    Converte i PDF/raw in markdown strutturato, salva tutto nella cartella book (md_output_path).
    Args:
        config: oggetto TimmyConfig (deve avere .md_output_path_path)
        mapping: dict di mapping semantico
    """
    md_dir = config.md_output_path_path
    raw_dir = config.raw_dir_path
    md_dir.mkdir(parents=True, exist_ok=True)

    # Esempio: per ogni file raw
    for pdf_file in raw_dir.glob("*.pdf"):
        # Conversione e salvataggio (dummy per esempio)
        md_path = md_dir / (pdf_file.stem + ".md")
        # Esegui qui la conversione reale (parser, extraction, mapping...)
        with open(md_path, "w", encoding="utf-8") as out_md:
            out_md.write(f"# Markdown per {pdf_file.name}\n")
        logging.info(f"Creato file markdown: {md_path}")

def generate_summary_markdown(md_files, md_dir):
    """
    Genera il file SUMMARY.md nella cartella markdown (book).
    Args:
        md_files: lista di Path dei markdown generati
        md_dir: Path della cartella markdown (usare config.md_output_path_path)
    """
    summary_path = md_dir / "SUMMARY.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# Summary\n\n")
        for md_file in md_files:
            f.write(f"* [{md_file.stem}]({md_file.name})\n")
    logging.info(f"Creato SUMMARY.md in {summary_path}")

def generate_readme_markdown(md_dir):
    """
    Genera il file README.md nella cartella markdown (book).
    Args:
        md_dir: Path della cartella markdown (usare config.md_output_path_path)
    """
    readme_path = md_dir / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# Documentazione Timmy-KB\n")
    logging.info(f"Creato README.md in {readme_path}")

# Esempio di funzione di post-processing o validazione path
def validate_markdown_dir(md_dir):
    """
    Verifica che la cartella markdown esista e sia scrivibile.
    Args:
        md_dir: Path della cartella markdown (usare config.md_output_path_path)
    """
    if not md_dir.exists():
        raise FileNotFoundError(f"La cartella markdown non esiste: {md_dir}")
    if not md_dir.is_dir():
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")

# Tutte le chiamate a queste utility nei consumer devono ora passare SOLO config.md_output_path_path!
