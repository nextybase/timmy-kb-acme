#!/usr/bin/env python3
"""
Conversione PDF → Markdown, con metadati semantici, immagini,
NLP, estrazione entità/relazioni e supporto struttura cartelle.
"""

import os
import sys
import re
import json
import yaml
import logging
from pathlib import Path
import fitz  # PyMuPDF
from slugify import slugify

try:
    import spacy
    nlp = spacy.load("it_core_news_sm")
except Exception:
    nlp = None
    print("⚠️ NLP disattivato: spaCy o modello mancante.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
SRC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_ROOT))
from ingest.config_loader import load_config
from ingest.semantic_extractor import (
    estrai_entita,
    estrai_relazioni,
    arricchisci_entita_con_contesto,
)

# ──────────────────────────────────────────────────────────────
def get_semantic_context_from_path(pdf_path: Path, base_input_dir: Path) -> dict:
    config_dir = Path(__file__).resolve().parents[2] / "config"
    structure_path = config_dir / "raw_structure.yaml"

    try:
        with open(structure_path, "r", encoding="utf-8") as f:
            struttura = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("⚠️ raw_structure.yaml non trovato in config/.")
        return {}

    try:
        rel = pdf_path.relative_to(base_input_dir)
        category = rel.parts[0].lower()
    except Exception:
        return {}

    return struttura.get(category, {})

def apply_nlp_enhancement(text: str) -> str:
    if not nlp:
        return text
    doc = nlp(text)
    enhanced = []
    for sent in doc.sents:
        s = sent.text.strip()
        if len(s) < 60 and not any(tok.pos_ == "VERB" for tok in sent):
            enhanced.append(f"## {s}")
        else:
            enhanced.append(s)
    return "\n\n".join(enhanced)

def is_subtitle(line: str) -> bool:
    words = line.strip().split()
    return len(words) >= 3 and line == line.upper() and line.replace(" ", "").isalpha() and len(line.strip()) > 12

def clean_markdown(text: str, title: str) -> str:
    lines = text.splitlines()
    cleaned = []
    skip_blank = False
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and lines[idx].strip().lower() == title.strip().lower():
        lines[idx] = ''
    for line in lines:
        line = line.rstrip()
        if re.match(r"^\s*pagina\s*\d+", line.lower()):
            continue
        if re.match(r"^\s*[●•\-*]\s+", line):
            line = re.sub(r"^\s*[●•\-*]\s+", "- ", line)
        if is_subtitle(line):
            line = f"## {line.title()}"
        if not line.strip():
            if skip_blank:
                continue
            skip_blank = True
        else:
            skip_blank = False
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def genera_markdown_semantico(entita, relazioni) -> str:
    md = ""
    if entita:
        md += "\n\n## 🧩 Entità rilevate\n\n"
        md += "| Tipo       | Nome              |\n"
        md += "|------------|-------------------|\n"
        for e in entita:
            md += f"| {e['tipo']:11} | {e['valore']} |\n"
    if relazioni:
        md += "\n\n## 🔗 Relazioni Semantiche\n\n"
        for s, r, o in relazioni:
            md += f"- {s} **{r}** {o}\n"
    return md

def salva_output_json(json_path: Path, entita, relazioni):
    data = {
        "entita": entita,
        "relazioni": [
            {"soggetto": s, "relazione": r, "oggetto": o}
            for s, r, o in relazioni
        ]
    }
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ──────────────────────────────────────────────────────────────
def convert_pdf_to_md(pdf_path: Path, md_path: Path, base_input_dir: Path) -> bool:
    try:
        doc = fitz.open(str(pdf_path))
        lines = []
        for page_num, page in enumerate(doc, start=1):
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") == 0:
                    for line in block["lines"]:
                        line_text = " ".join([span["text"] for span in line["spans"]]).strip()
                        if not line_text:
                            continue
                        font_size = max(span["size"] for span in line["spans"])
                        if font_size >= 16 and line_text == line_text.upper():
                            lines.append(f"## {line_text.title()}")
                        else:
                            lines.append(line_text)
                elif block.get("type") == 1:
                    lines.append(f"[📷 Immagine rilevata a pagina {page_num}]")

        raw_text = "\n\n".join(lines).strip()
        title = pdf_path.stem.replace('-', ' ').replace('_', ' ').title()
        slug = slugify(title)

        semantic_context = get_semantic_context_from_path(pdf_path, Path(base_input_dir))

        frontmatter = (
            f"---\n"
            f"title: \"{title}\"\n"
            f"slug: \"{slug}\"\n"
            f"source_file: \"{pdf_path.name}\"\n"
        )
        if semantic_context:
            rel = pdf_path.relative_to(Path(base_input_dir))
            frontmatter += f"domain: \"{rel.parts[0]}\"\n"
            if "tipo_contenuto" in semantic_context:
                tipi = ", ".join(semantic_context["tipo_contenuto"])
                frontmatter += f"tipo_contenuto: [{tipi}]\n"
            if "entita_rilevanti" in semantic_context:
                entita_context = ", ".join(semantic_context["entita_rilevanti"])
                frontmatter += f"entita_rilevanti: [{entita_context}]\n"
        frontmatter += "---\n\n"

        enhanced = apply_nlp_enhancement(raw_text)
        markdown = clean_markdown(enhanced, title)

        entita = estrai_entita(raw_text)
        entita = arricchisci_entita_con_contesto(entita, semantic_context)
        relazioni = estrai_relazioni(raw_text)
        semantico = genera_markdown_semantico(entita, relazioni)

        full_md = frontmatter + f"# {title}\n\n" + markdown + semantico

        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(full_md, encoding='utf-8')
        salva_output_json(md_path.with_suffix(".json"), entita, relazioni)

        return True

    except Exception as e:
        logger.error(f"[ERRORE] {pdf_path.name} non convertibile: {e}")
        return False

# ──────────────────────────────────────────────────────────────
def convert_pdfs_to_markdown(config: dict):
    raw_dir = Path(config["drive_input_path"]).resolve()
    out_dir = Path(config["md_output_path"]).resolve()

    if not raw_dir.exists() or not raw_dir.is_dir():
        logger.fatal(f"📂 Directory sorgente PDF non valida: {raw_dir}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_files = list(raw_dir.rglob("*.pdf"))
    total = len(raw_files)
    failed = []

    logger.info(f"📥 Trovati {total} PDF da convertire in {raw_dir}")

    for pdf in raw_files:
        rel_path = pdf.relative_to(raw_dir).with_suffix(".md")
        out_md = out_dir / rel_path
        logger.info(f"📄 {pdf.name} → {out_md}")
        if not convert_pdf_to_md(pdf, out_md, raw_dir):
            failed.append(str(pdf))

    logger.info(f"✅ Conversione completata: {total - len(failed)}/{total} riusciti")
    if failed:
        logger.warning("🚫 File non convertiti:\n" + "\n".join(failed))

if __name__ == "__main__":
    config = load_config()
    convert_pdfs_to_markdown(config)
