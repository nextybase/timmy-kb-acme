# src/ingest/semantic_extractor.py

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def extract_semantics(config: dict):
    """
    Estrae metadati e struttura semantica dai file .md generati.
    Attualmente crea placeholder README.json e SUMMARY.json.
    In futuro, implementerà il parsing semantico dei contenuti Markdown.
    """
    output_path = Path(config["md_output_path"])
    if not output_path.exists():
        logger.error(f"❌ Path di output non trovato: {output_path}")
        return

    md_files = sorted(output_path.glob("*.md"))
    if not md_files:
        logger.warning("⚠️ Nessun file .md trovato per l’estrazione semantica.")
        return

    # ✅ Naming coerente con trattino per repo
    slug = config.get("slug")
    repo_name = f"timmy-kb-{slug}"
    config["repo_name"] = repo_name  # 🔁 esplicito se non già presente

    summary = {
        "slug": slug,
        "repo_name": repo_name,
        "files": [f.name for f in md_files]
    }

    # File README.json
    readme_json = output_path / "README.json"
    with open(readme_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info(f"📄 Semantica estratta: {readme_json.name}")

    # File SUMMARY.json
    summary_json = output_path / "SUMMARY.json"
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info(f"📄 Semantica estratta: {summary_json.name}")
