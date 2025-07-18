import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def _titolo_from_filename(filename: str) -> str:
    nome = Path(filename).stem
    nome = nome.replace("_", " ").replace("-", " ")
    nome = nome.lower().capitalize()
    return nome

def build_markdown_summary(config: dict):
    output_path = Path(config["md_output_path"])
    if not output_path.exists():
        raise FileNotFoundError(f"❌ Output path non trovato: {output_path}")

    md_files = sorted(output_path.glob("*.md"))
    md_files = [f for f in md_files if f.name.lower() not in {"readme.md", "summary.md"}]

    links = [f"* [{_titolo_from_filename(f.name)}](./{f.name})" for f in md_files]

    summary_file = output_path / "SUMMARY.md"
    summary_file.write_text("# Summary\n\n" + "\n".join(links), encoding="utf-8")
    logger.info(f"SUMMARY.md generato con {len(links)} file.")

    readme_path = output_path / "README.md"
    if not readme_path.exists() or readme_path.stat().st_size == 0:
        readme_path.write_text("# Documentazione\n\nBenvenuto nella Knowledge Base.", encoding="utf-8")
        logger.info("✅ README.md generato con contenuto minimale.")
    else:
        logger.info("README.md aggiornato.")
