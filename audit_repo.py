# audit_repo.py
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.getcwd())

README_CANDIDATES = ["README.md", "README.rst", "readme.md", "Readme.md"]
DOC_HINTS = {
    "mkdocs": ["mkdocs.yml"],
    "sphinx": ["docs/conf.py", "source/conf.py"],
    "gitbook": ["docs/SUMMARY.md", "SUMMARY.md", "book.json"],
}
PY_HINTS = {
    "pyproject": ["pyproject.toml"],
    "setup_cfg": ["setup.cfg"],
    "requirements": ["requirements.txt", "requirements/*.txt"],
    "src_layout": ["src"],
    "tests": ["tests", "test", "pytest.ini", "tox.ini"],
    "lint": [".flake8", ".ruff.toml", ".pylintrc"],
    "ci": [".github/workflows", ".gitlab-ci.yml"],
}


def glob_exists(pattern):
    return any(ROOT.glob(pattern)) if any(c in pattern for c in "*?[]") else (ROOT / pattern).exists()


def detect_stack():
    docs = {k: any(glob_exists(p) for p in v) for k, v in DOC_HINTS.items()}
    py = {k: any(glob_exists(p) for p in v) for k, v in PY_HINTS.items()}
    return docs, py


def read_readme():
    for name in README_CANDIDATES:
        p = ROOT / name
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="ignore")
            return name, text
    return None, ""


def parse_readme(md):
    # titoli
    titles = [ln.strip() for ln in md.splitlines() if ln.strip().startswith("#")]
    # badge (immagini in link)
    badge_re = re.compile(r"!\[.*?\]\((.*?)\)")
    badges = badge_re.findall(md)
    # sezioni principali (#, ##)
    sections = [ln.strip().lstrip("#").strip() for ln in md.splitlines() if re.match(r"^#{1,2}\s", ln)]
    words = len(re.findall(r"\b\w+\b", md))
    return {"headings": titles, "sections": sections, "badges": badges, "word_count": words}


def list_tree(max_depth=3, ignore_dirs=None):
    if ignore_dirs is None:
        ignore_dirs = {
            ".git",
            ".venv",
            "venv",
            ".mypy_cache",
            ".ruff_cache",
            "__pycache__",
            ".pytest_cache",
            "node_modules",
        }
    tree = []
    for root, dirs, files in os.walk(ROOT):
        rel = Path(root).relative_to(ROOT)
        depth = len(rel.parts)
        # prune
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".") or d in (".github",)]
        if depth > max_depth:
            continue
        tree.append(
            {
                "path": str(rel) if str(rel) != "." else ".",
                "dirs": sorted(dirs),
                "files": sorted(files[:200]),  # cap to keep it readable
            }
        )
    return tree


def docs_inventory():
    d = ROOT / "docs"
    out = {"exists": d.exists(), "files": [], "top_md": []}
    if d.exists():
        for p in d.rglob("*"):
            if p.is_file():
                out["files"].append(str(p.relative_to(ROOT)))
                if p.parent == d and p.suffix.lower() in {".md", ".rst"}:
                    out["top_md"].append(str(p.relative_to(ROOT)))
    return out


def main():
    docs_flags, py_flags = detect_stack()
    readme_name, readme_text = read_readme()
    readme_info = parse_readme(readme_text) if readme_text else None

    report = {
        "root": str(ROOT),
        "python_stack": py_flags,
        "docs_stack": docs_flags,
        "has_docs_dir": (ROOT / "docs").exists(),
        "docs_inventory": docs_inventory(),
        "readme": {"file": readme_name, **(readme_info or {})},
        "tree": list_tree(),
        "quick_findings": [],
    }

    # quick opinions
    if not py_flags["pyproject"] and (ROOT / "setup.py").exists() is False:
        report["quick_findings"].append("Assente pyproject.toml: consigliata migrazione a PEP 621.")
    if report["docs_stack"]["gitbook"] and (ROOT / "mkdocs.yml").exists():
        report["quick_findings"].append("Sovrapposizione GitBook/MkDocs: scegliere uno solo per evitare drift.")
    if report["docs_inventory"]["exists"] and not report["docs_inventory"]["top_md"]:
        report["quick_findings"].append("docs/ presente ma senza index/README di primo livello.")
    if py_flags["tests"] is False:
        report["quick_findings"].append("Mancano test o configurazione di test: introdurre pytest.")
    if py_flags["lint"] is False:
        report["quick_findings"].append("Nessuna config lint/format: aggiungere Ruff/Black e pre-commit.")
    if py_flags["ci"] is False:
        report["quick_findings"].append("Assente CI: aggiungere workflow base (lint+tests).")

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
