import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pathlib import Path
import importlib.util

# Import dinamico
mapping_path = os.path.join(os.path.dirname(__file__), "semantic_mapping.py")
spec = importlib.util.spec_from_file_location("semantic_mapping", mapping_path)
semantic_mapping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(semantic_mapping)
get_semantic_info_for_file = semantic_mapping.get_semantic_info_for_file

# Import build_summary
build_summary_path = os.path.join(os.path.dirname(__file__), "..", "ingest", "build_summary.py")
spec2 = importlib.util.spec_from_file_location("build_summary", build_summary_path)
build_summary = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(build_summary)

def clean_top_level_markdown(folder_path):
    folder = Path(folder_path)
    for p in folder.glob("*.md"):
        try:
            p.unlink()
            print(f"🗑️  Cancellato: {p.name}")
        except Exception as e:
            print(f"⚠️  Impossibile cancellare {p.name}: {e}")

def convert_pdf_to_md(pdf_path, output_path, sem_info):
    """
    Semplice placeholder: crea un markdown arricchito a partire dal nome del PDF.
    (Qui puoi integrare il vero parser PDF→MD)
    """
    md_name = Path(pdf_path).stem.replace(" ", "_") + ".md"
    md_path = Path(output_path) / md_name
    content = f"# Contenuto fittizio per {Path(pdf_path).name}\n"
    fm_lines = [
        "---",
        f"ambito: \"{sem_info.get('ambito', 'unknown')}\"",
        f'descrizione: "{sem_info.get("descrizione", "")}"',
        "---\n"
    ]
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(fm_lines) + content)
    print(f"✅ {md_path} creato e arricchito.")

def enrich_from_pdf(raw_folder, output_folder):
    raw_dir = Path(raw_folder)
    output_dir = Path(output_folder)
    pdf_files = list(raw_dir.rglob("*.pdf"))
    print(f"🧠 Conversione e enrichment di {len(pdf_files)} PDF...")
    for pdf in pdf_files:
        # Ricava la cartella semantica (primo sottofolder dopo /raw)
        parts = pdf.relative_to(raw_dir).parts
        folder = parts[0] if len(parts) > 1 else ""
        sem_info = get_semantic_info_for_file(folder)
        convert_pdf_to_md(pdf, output_dir, sem_info)

def regenerate_summary_readme(output_folder, slug):
    output_dir = Path(output_folder)
    md_files = [f.name for f in output_dir.glob("*.md") if f.suffix == ".md"]
    build_summary.generate_summary_md(md_files, str(output_dir))
    build_summary.generate_readme_md(str(output_dir), slug)
    print("📑 SUMMARY.md e README.md rigenerati.")

if __name__ == "__main__":
    if len(sys.argv) > 2:
        out_folder = sys.argv[1]
        slug = sys.argv[2]
        raw_folder = Path(out_folder) / "raw"
    else:
        out_folder = input("Cartella output cliente: ").strip()
        slug = input("Slug cliente: ").strip()
        raw_folder = Path(out_folder) / "raw"

    scelta = input("Vuoi cancellare i file .md nella cartella principale (inclusi README.md e SUMMARY.md)? [y/N] ").strip().lower()
    if scelta == "y":
        clean_top_level_markdown(out_folder)

    enrich_from_pdf(raw_folder, out_folder)
    regenerate_summary_readme(out_folder, slug)
