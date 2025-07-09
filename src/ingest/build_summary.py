import os
import yaml
import sys

# Importa il loader di config centralizzato
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ingest.config_loader import load_config

cfg = load_config()
MD_ROOT = cfg['md_output_path']
SUMMARY_PATH = os.path.join(MD_ROOT, "SUMMARY.md")
README_PATH = os.path.join(MD_ROOT, "README.md")

def get_title_from_md(md_path):
    """Estrae il titolo dal front matter YAML o dal titolo H1."""
    try:
        with open(md_path, encoding="utf-8") as f:
            lines = f.readlines()
            if lines and lines[0].startswith("---"):
                yaml_block = []
                for line in lines[1:]:
                    if line.startswith("---"):
                        break
                    yaml_block.append(line)
                meta = yaml.safe_load("".join(yaml_block))
                if meta and "title" in meta:
                    return str(meta["title"]).strip()
            # Fallback: cerca prima linea che inizia con "#"
            for line in lines:
                if line.strip().startswith("# "):
                    return line.strip("# ").strip()
    except Exception:
        return os.path.splitext(os.path.basename(md_path))[0]
    return os.path.splitext(os.path.basename(md_path))[0]

def build_summary():
    entries = []
    for root, dirs, files in os.walk(MD_ROOT):
        dirs.sort()
        files = sorted([f for f in files if f.endswith(".md")])
        rel_root = os.path.relpath(root, MD_ROOT)
        indent_level = 0 if rel_root == "." else rel_root.count(os.sep) + 1

        if rel_root != ".":
            sezione = os.path.basename(root).replace("-", " ").title()
            entries.append("  " * (indent_level - 1) + f"- **{sezione}**")

        for f in files:
            md_path = os.path.join(root, f)
            rel_path = os.path.relpath(md_path, ".")
            title = get_title_from_md(md_path)
            entries.append("  " * indent_level + f"- [{title}]({rel_path.replace(os.sep, '/')})")

    # Intestazione
    lines = ["# Sommario", ""]
    lines.extend(entries)

    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ SUMMARY.md generato con {len(entries)} voci.")

if __name__ == "__main__":
    build_summary()
