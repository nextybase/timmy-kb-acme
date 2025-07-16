# -*- coding: utf-8 -*-
"""
Generazione automatica di SUMMARY.md e README.md da file Markdown.
Compatibile con GitBook (navigazione laterale).
"""

import logging
from pathlib import Path
import yaml
from collections import defaultdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def extract_title(md_path: Path) -> str:
    """Estrae titolo da front matter YAML o primo H1"""
    try:
        lines = md_path.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].strip() == "---":
            yaml_block = []
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                yaml_block.append(line)
            meta = yaml.safe_load("\n".join(yaml_block))
            if isinstance(meta, dict) and "title" in meta:
                return str(meta["title"]).strip()
        for line in lines:
            if line.strip().startswith("# "):
                return line.strip().lstrip("#").strip()
    except Exception as e:
        logger.warning(f"⚠️ Titolo non estratto da {md_path.name}: {e}")
    return md_path.stem.replace("-", " ").replace("_", " ").title()

def build_markdown_summary(config: dict) -> None:
    md_root = Path(config["md_output_path"]).resolve()
    summary_file = md_root / "SUMMARY.md"
    readme_file = md_root / "README.md"

    # Mappa sezioni → lista file
    sections = defaultdict(list)

    for path in sorted(md_root.rglob("*.md")):
        if path.name.lower() in {"summary.md", "readme.md"}:
            continue

        rel = path.relative_to(md_root)
        section = rel.parts[0] if len(rel.parts) > 1 else "root"
        sections[section].append(rel)

    content = ["# Summary", "", "* [Introduzione](README.md)"]

    for section, files in sorted(sections.items()):
        if section != "root":
            content.append(f"* [{section.title()}]()")
        for rel in files:
            title = extract_title(md_root / rel)
            indent = "  " if section != "root" else ""
            content.append(f"{indent}* [{title}]({rel.as_posix()})")

    summary_file.write_text("\n".join(content), encoding="utf-8")
    readme_file.write_text("\n".join(content), encoding="utf-8")

    logger.info(f"✅ SUMMARY.md generato con {sum(len(f) for f in sections.values())} file.")
    logger.info("📄 README.md aggiornato.")
