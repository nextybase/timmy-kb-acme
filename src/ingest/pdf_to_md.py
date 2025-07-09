import os
import fitz  # PyMuPDF
from slugify import slugify
import re
import sys

# Importa il loader di config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ingest.config_loader import load_config

cfg = load_config()

RAW_DIR = cfg['drive_input_path']
OUTPUT_DIR = cfg['md_output_path']

def is_subtitle(line):
    words = line.strip().split()
    return (
        len(words) >= 3
        and line == line.upper()
        and line.replace(" ", "").isalpha()
        and len(line.strip()) > 12
    )

def clean_markdown(text, title):
    lines = text.splitlines()
    cleaned_lines = []
    skip_next_blank = False
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].strip().lower() == title.strip().lower():
        lines[idx] = ""
    for i, line in enumerate(lines):
        orig = line
        line = line.rstrip()
        if re.match(r"^\s*pagina\s*\d+", line.lower()):
            continue
        if re.match(r"^\s*[●•\-\*]\s+", line):
            line = re.sub(r"^\s*[●•\-\*]\s+", "- ", line)
        if is_subtitle(line):
            line = f"## {line.title()}"
        if line.strip() == "":
            if skip_next_blank:
                continue
            skip_next_blank = True
        else:
            skip_next_blank = False
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text.strip()

def convert_pdf_to_md(pdf_path, output_path, title):
    slug = slugify(title)
    raw_text = extract_text_from_pdf(pdf_path)
    clean_text = clean_markdown(raw_text, title)
    main_title = "# " + title + "\n\n"
    front_matter = f"---\ntitle: \"{title}\"\nslug: \"{slug}\"\nsource_file: \"{os.path.basename(pdf_path)}\"\n---\n\n"
    full_content = front_matter + main_title + clean_text
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_content)

def process_all_pdfs():
    for root, _, files in os.walk(RAW_DIR):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_path = os.path.join(root, file)
                relative_path = os.path.relpath(pdf_path, RAW_DIR)
                relative_dir = os.path.dirname(relative_path)
                output_dir = os.path.join(OUTPUT_DIR, relative_dir)
                os.makedirs(output_dir, exist_ok=True)
                slug_name = slugify(os.path.splitext(file)[0]) + ".md"
                output_path = os.path.join(output_dir, slug_name)
                title = os.path.splitext(file)[0].replace("-", " ").replace("_", " ").title()
                print(f"📝 Converting: {pdf_path} → {output_path}")
                convert_pdf_to_md(pdf_path, output_path, title)

if __name__ == "__main__":
    process_all_pdfs()
    print("✅ Conversione raffinata completata.")
