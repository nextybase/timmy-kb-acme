import yaml
from pathlib import Path
import fitz  # PyMuPDF
import re
from pipeline.exceptions import ConversionError
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.file2md_utils")

def load_tags_by_category(path="config/timmy_tags.yaml"):
    """Carica la lista di tag strutturata per categorie dal file YAML."""
    try:
        with open(path, encoding="utf-8") as f:
            cats = yaml.safe_load(f)
        return cats
    except Exception as e:
        logger.error(f"❌ Errore nel caricamento dei tag da {path}: {e}")
        raise ConversionError(f"Errore nel caricamento dei tag da {path}: {e}")

def get_all_tags(tags_by_cat):
    """Ritorna tutte le stringhe tag uniche (lowercase)."""
    alltags = []
    for tags in tags_by_cat.values():
        alltags.extend(tags)
    return list(set([t.lower() for t in alltags]))

def get_paragraph_tags(paragraph, tags_by_cat):
    """Effettua matching multi-word di tag all'interno del paragrafo."""
    paragraph_norm = paragraph.lower().replace("-", " ").replace("_", " ")
    matches = set()
    for cat, tags in tags_by_cat.items():
        for tag in tags:
            tag_norm = tag.lower().replace("-", " ").replace("_", " ")
            if tag_norm in paragraph_norm:
                matches.add(tag)
    return list(matches)

def markdownize_pdf_text(raw_text: str, tags_by_cat=None) -> str:
    """
    Suddivide il testo in blocchi tra righe vuote.
    Riconosce titoli reali, elenchi, paragrafi.
    Unisce frasi spezzate. Inserisce tag a fine paragrafo.
    """
    lines = [l.rstrip() for l in raw_text.splitlines()]
    blocks = []
    buffer = []

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
        is_heading = (
            len(first) < 60 and (
                first.isupper() or
                first.endswith(":") or
                (len(block) == 1)
            )
        )
        paragraph = ""
        if is_heading:
            result.append(f"## {first}")
            if len(block) > 1:
                paragraph = " ".join(l.strip() for l in block[1:])
        else:
            paragraph = " ".join(l.strip() for l in block)

        if paragraph:
            tag_line = ""
            if tags_by_cat is not None:
                tags = get_paragraph_tags(paragraph, tags_by_cat)
                if tags:
                    tag_line = f"\n<!-- tags: {', '.join(tags)} -->"
            result.append(paragraph + tag_line)

    return "\n\n".join(result)

def build_frontmatter(pdf_path: Path, mapping=None, config=None):
    """
    Costruisce il frontmatter YAML a partire dal nome file e parametri extra.
    """
    frontmatter = {
        "titolo": pdf_path.stem,
        "origine_file": str(pdf_path),
    }
    if config and "slug" in config:
        frontmatter["slug_cliente"] = config["slug"]
    if mapping:
        # Implementa mapping semantico (placeholder)
        frontmatter["categoria"] = mapping.get(pdf_path.parent.name, "documento")
    return frontmatter

def extract_pdf_blocks_to_markdown(pdf_path: Path, md_output_path: Path, frontmatter: dict, tags_by_cat=None):
    """
    Estrae testo da un PDF e lo trasforma in markdown, scrivendo il file in md_output_path.
    """
    try:
        doc = fitz.open(pdf_path)
        content = []
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text().strip()
            if page_text:
                page_text_md = markdownize_pdf_text(page_text, tags_by_cat=tags_by_cat)
                content.append(page_text_md)
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
        logger.info(f"✅ Conversione completata: {md_file.name}")
    except Exception as e:
        logger.error(f"❌ Errore durante l'estrazione PDF→Markdown di {pdf_path}: {e}")
        raise ConversionError(f"Errore durante l'estrazione PDF→Markdown di {pdf_path}: {e}")

def extract_file_to_markdown(path: Path, md_output_path: Path, frontmatter: dict, tags_by_cat=None):
    """
    Estrae contenuto da un file supportato e salva come Markdown in md_output_path.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        extract_pdf_blocks_to_markdown(path, md_output_path, frontmatter, tags_by_cat=tags_by_cat)
    # TODO: elif suffix == ".docx": ...
    # TODO: elif suffix in [".jpg", ".png"]: ...
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
            logger.warning(f"⚠️ Tipo file non supportato per estrazione automatica: {path}")
            raise ConversionError(f"Tipo file non supportato: {path.suffix}")
        except Exception as e:
            logger.error(f"❌ Errore durante l'estrazione file→Markdown di {path}: {e}")
            raise ConversionError(f"Errore durante l'estrazione file→Markdown di {path}: {e}")

def convert_pdfs_to_markdown(pdf_root, md_output_path, mapping=None, config=None, tags_by_cat=None):
    """
    Funzione pubblica principale: trova tutti i PDF in pdf_root (ricorsivo) e li converte in Markdown,
    salvandoli SOLO in md_output_path, con filename minuscolo/underscore.
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
