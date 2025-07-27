import yaml
from pathlib import Path
import fitz  # PyMuPDF
import re
from typing import Optional, Dict, List

from pipeline.exceptions import ConversionError
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.file2md_utils")


def load_tags_by_category(path: str = "config/timmy_tags.yaml") -> Dict[str, List[str]]:
    """Carica i tag semantici da YAML strutturato per categorie."""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Errore nel caricamento dei tag da {path}: {e}")
        raise ConversionError(f"Errore nel caricamento dei tag da {path}: {e}")

def get_all_tags(tags_by_cat: Dict[str, List[str]]) -> List[str]:
    """Ritorna la lista unica di tutti i tag (lowercase)."""
    return list({tag.lower() for tags in tags_by_cat.values() for tag in tags})

def get_paragraph_tags(paragraph: str, tags_by_cat: Dict[str, List[str]]) -> List[str]:
    """Esegue matching dei tag all'interno di un paragrafo normalizzato."""
    paragraph_norm = paragraph.lower().replace("-", " ").replace("_", " ")
    matches = set()
    for taglist in tags_by_cat.values():
        for tag in taglist:
            tag_norm = tag.lower().replace("-", " ").replace("_", " ")
            if tag_norm in paragraph_norm:
                matches.add(tag)
    return list(matches)

def markdownize_pdf_text(raw_text: str, tags_by_cat: Optional[Dict[str, List[str]]] = None) -> str:
    """Trasforma testo PDF in Markdown arricchito di heading, elenchi e tag semantici."""
    lines = [l.rstrip() for l in raw_text.splitlines()]
    blocks, buffer = [], []

    for line in lines:
        if not line.strip():
            if buffer:
                blocks.append(buffer)
                buffer = []
        else:
            buffer.append(line)
    if buffer:
        blocks.append(buffer)

    result = []
    for block in blocks:
        if all(re.match(r"^(\d+[\.\)]|[•\-–])\s+", l) for l in block):
            for l in block:
                item = re.sub(r"^(\d+[\.\)]|[•\-–])\s*", "- ", l.strip())
                result.append(item)
            continue

        first = block[0].strip()
        is_heading = len(first) < 60 and (first.isupper() or first.endswith(":") or len(block) == 1)
        paragraph = " ".join(l.strip() for l in (block[1:] if is_heading else block))

        if is_heading:
            result.append(f"## {first}")
        if paragraph:
            tag_line = ""
            if tags_by_cat:
                tags = get_paragraph_tags(paragraph, tags_by_cat)
                if tags:
                    tag_line = f"\n<!-- tags: {', '.join(tags)} -->"
            result.append(paragraph + tag_line)

    return "\n\n".join(result)

def build_frontmatter(pdf_path: Path, mapping: Optional[Dict[str, str]] = None, config: Optional[Dict] = None) -> Dict:
    """Costruisce frontmatter YAML a partire da nome file e mappa semantica."""
    frontmatter = {
        "titolo": pdf_path.stem,
        "origine_file": str(pdf_path),
    }
    if config and "slug" in config:
        frontmatter["slug_cliente"] = config["slug"]
    if mapping:
        frontmatter["categoria"] = mapping.get(pdf_path.parent.name, "documento")
    return frontmatter

def extract_pdf_blocks_to_markdown(
    pdf_path: Path,
    md_output_path: Path,
    frontmatter: Dict,
    tags_by_cat: Optional[Dict[str, List[str]]] = None
) -> None:
    """Estrae il contenuto testuale di un PDF e lo salva come file Markdown completo di frontmatter."""
    try:
        doc = fitz.open(pdf_path)
        content = [
            markdownize_pdf_text(page.get_text().strip(), tags_by_cat=tags_by_cat)
            for page in doc if page.get_text().strip()
        ]
        doc.close()

        full_text = "\n\n".join(content) if content else "*Nessun testo trovato nel PDF*"
        md_content = (
            "---\n"
            + yaml.dump(frontmatter, allow_unicode=True)
            + "---\n"
            f"# {frontmatter.get('titolo', pdf_path.stem)}\n"
            f"{full_text}"
        )
        md_name = pdf_path.stem.replace(" ", "_").lower() + ".md"
        md_file = md_output_path / md_name
        md_file.write_text(md_content, encoding="utf-8")
        logger.info(f"✅ PDF convertito: {md_file.name}")
    except Exception as e:
        logger.error(f"❌ Errore PDF→Markdown ({pdf_path}): {e}")
        raise ConversionError(f"Errore PDF→Markdown: {e}")

def extract_file_to_markdown(
    path: Path,
    md_output_path: Path,
    frontmatter: Dict,
    tags_by_cat: Optional[Dict[str, List[str]]] = None
) -> None:
    """Wrapper per supportare in futuro anche altri formati (.docx, .png, ecc.)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        extract_pdf_blocks_to_markdown(path, md_output_path, frontmatter, tags_by_cat=tags_by_cat)
    else:
        try:
            md_content = (
                "---\n"
                + yaml.dump(frontmatter, allow_unicode=True)
                + "---\n"
                f"# {frontmatter.get('titolo', path.stem)}\n"
                "*Tipo file non supportato per estrazione automatica.*"
            )
            md_name = path.stem.replace(" ", "_").lower() + ".md"
            md_file = md_output_path / md_name
            md_file.write_text(md_content, encoding="utf-8")
            logger.warning(f"⚠️ File non supportato per estrazione automatica: {path.name}")
            raise ConversionError(f"Tipo file non supportato: {path.suffix}")
        except Exception as e:
            logger.error(f"❌ Errore file→Markdown ({path}): {e}")
            raise ConversionError(f"Errore file→Markdown: {e}")

def convert_pdfs_to_markdown(
    pdf_root: Path,
    md_output_path: Path,
    mapping: Optional[Dict] = None,
    config: Optional[Dict] = None,
    tags_by_cat: Optional[Dict[str, List[str]]] = None
) -> int:
    """
    Converte ricorsivamente tutti i PDF nella cartella `pdf_root` in file Markdown.
    Salva l'output nella cartella `md_output_path`.
    """
    pdf_root = Path(pdf_root)
    md_output_path = Path(md_output_path)
    md_output_path.mkdir(parents=True, exist_ok=True)

    pdf_files = list(pdf_root.rglob("*.pdf"))
    if not pdf_files:
        logger.warning(f"⚠️ Nessun PDF trovato in {pdf_root}")

    for pdf_path in pdf_files:
        frontmatter = build_frontmatter(pdf_path, mapping=mapping, config=config)
        extract_pdf_blocks_to_markdown(pdf_path, md_output_path, frontmatter, tags_by_cat=tags_by_cat)

    return len(pdf_files)
