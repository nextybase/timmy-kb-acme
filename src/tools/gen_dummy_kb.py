# src/tools/gen_dummy_kb.py
from __future__ import annotations

# --- PYTHONPATH bootstrap (consente import "pipeline.*" quando esegui da src/tools) ---
import sys as _sys
from pathlib import Path as _P
_SRC_DIR = _P(__file__).resolve().parents[1]  # .../src
if str(_SRC_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SRC_DIR))
# --------------------------------------------------------------------------------------

import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import is_safe_subpath
from pipeline.exceptions import ConfigError, EXIT_CODES

logger = get_structured_logger("tools.gen_dummy_kb")

# Dipendenze opzionali
try:
    from fpdf import FPDF  # type: ignore
except Exception:
    FPDF = None  # fallback: generiamo .txt
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    # Non bloccante: le env verranno lette solo se già settate
    pass

# Costanti e risorse
DUMMY_SLUG = "dummy"
RAW_YAML_REL = "config/cartelle_raw.yaml"
PDF_YAML_REL = "config/pdf_dummy.yaml"

# ID reali della cartella dummy su Drive (per test)
HARDCODED_DUMMY_DRIVE_ID = "1C1L-BtruPfyQB3nZCeo6zpjm0g77O95J"
HARDCODED_DUMMY_FOLDER_ID = "12cLba2kKKF4YH_JBA19Kjwr0J8awQDVh"


def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        import yaml
        return (yaml.safe_load(f) or {})  # type: ignore[no-any-return]


def _extract_cartelle(cartelle_yaml: Dict[str, Any]) -> List[str]:
    """Estrae le cartelle tematiche dalla struttura YAML `cartelle_raw.yaml`."""
    def _walk(nodes: List[Dict[str, Any]]) -> List[str]:
        acc: List[str] = []
        for item in nodes or []:
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                acc.append(name.strip())
            sub = item.get("subfolders") or []
            if isinstance(sub, list) and sub:
                acc += _walk(sub)
        return acc
    return _walk(cartelle_yaml.get("root_folders", []))


def _make_pdf(out_path: Path, titolo: str, paragrafi: List[str]) -> None:
    """Genera un PDF semplice; se FPDF non c'è, crea un .txt come placeholder."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if FPDF is None:
        placeholder = out_path.with_suffix(".txt")
        placeholder.write_text(f"# {titolo}\n\n" + "\n\n".join(paragrafi) + "\n", encoding="utf-8")
        logger.warning("FPDF non disponibile: creato placeholder .txt", extra={"file_path": str(placeholder)})
        return
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.multi_cell(0, 10, titolo)
    pdf.ln(6)
    pdf.set_font("Arial", "", 12)
    for par in paragrafi:
        pdf.multi_cell(0, 8, par)
        pdf.ln(2)
    pdf.output(str(out_path))
    logger.info("📄 PDF di test generato", extra={"file_path": str(out_path)})


def genera_raw_structure(raw_dir: Path, raw_yaml: Path, pdf_yaml: Path) -> None:
    """Genera la struttura RAW e i PDF dummy a partire dagli YAML di configurazione."""
    if not (raw_yaml.exists() and pdf_yaml.exists()):
        logger.warning(
            "YAML di configurazione non trovati: skip generazione RAW/PDF",
            extra={"raw_yaml": str(raw_yaml), "pdf_yaml": str(pdf_yaml)},
        )
        return

    cartelle_struct = load_yaml(raw_yaml)
    pdf_dummy = load_yaml(pdf_yaml)
    cartelle = _extract_cartelle(cartelle_struct)

    logger.info("🗂️  Genero struttura RAW con PDF dummy", extra={"dest": str(raw_dir), "cartelle": len(cartelle)})
    for cat in cartelle:
        cat_folder = raw_dir / cat
        if not is_safe_subpath(cat_folder, raw_dir.parent):
            logger.debug(f"Skip (path non sicuro): {cat_folder}", extra={"file_path": str(cat_folder)})
            continue
        cat_folder.mkdir(parents=True, exist_ok=True)
        info = pdf_dummy.get(cat, {})
        titolo = info.get("titolo", f"Sezione: {cat.title()}")
        paragrafi = info.get("paragrafi", [
            "Questo è un paragrafo di esempio.",
            "Puoi personalizzare il contenuto dei PDF modificando pdf_dummy.yaml.",
            "Sezione tematica generica.",
        ])
        pdf_path = cat_folder / f"{cat}_dummy.pdf"
        _make_pdf(pdf_path, titolo, paragrafi)

    logger.info("✅ PDF dummy generati", extra={"dest": str(raw_dir)})


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    base = project_root / "output" / f"timmy-kb-{DUMMY_SLUG}"
    book = base / "book"
    config_dir = base / "config"
    raw = base / "raw"
    dummy_repo = base / "repo"

    # Path sicurezza
    if not is_safe_subpath(base, project_root):
        logger.error("Base path non sicuro", extra={"file_path": str(base)})
        return EXIT_CODES.get("ConfigError", 2)

    # 1) Crea cartelle principali
    for folder in (book, config_dir, raw, dummy_repo):
        folder.mkdir(parents=True, exist_ok=True)

    # 2) Crea README/SUMMARY/test nel book
    (book / "README.md").write_text(
        "# Dummy KB – Test\n\nQuesta è una knowledge base di test generata automaticamente.\n",
        encoding="utf-8",
    )
    (book / "SUMMARY.md").write_text(
        "# Sommario\n\n* [Introduzione](README.md)\n* [Test Markdown](test.md)\n",
        encoding="utf-8",
    )
    (book / "test.md").write_text(
        "# Test Markdown\n\nQuesto è un file markdown di esempio per testare la pipeline Honkit.\n- Punto uno\n- Punto due\n",
        encoding="utf-8",
    )

    # 3) Crea config.yaml minimale
    cfg = {
        "slug": DUMMY_SLUG,
        "client_name": "Dummy KB",
        "raw_dir": str(raw),
        "md_output_path": str(book),
        "output_dir": str(base),
        "drive_id": HARDCODED_DUMMY_DRIVE_ID,
        "drive_folder_id": HARDCODED_DUMMY_FOLDER_ID,
        "service_account_file": os.environ.get("SERVICE_ACCOUNT_FILE", "service_account.json"),
        "base_drive": os.environ.get("BASE_DRIVE", "dummy-base-folder"),
        "github_repo": os.environ.get("GITHUB_REPO", "nextybase/timmy-kb-dummy"),
        "github_branch": os.environ.get("GITHUB_BRANCH", "main"),
        "github_token": os.environ.get("GITHUB_TOKEN", ""),
        "gitbook_token": os.environ.get("GITBOOK_TOKEN", ""),
    }
    import yaml
    with open(config_dir / "config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True)

    logger.info("✅ Cartella base KB generata", extra={"base": str(base)})

    # 4) Genera RAW da YAML + PDF
    raw_yaml = project_root / RAW_YAML_REL
    pdf_yaml = project_root / PDF_YAML_REL
    genera_raw_structure(raw, raw_yaml, pdf_yaml)

    # 5) Opzionale: crea cartella repo di test (interattivo, default NO)
    resp_repo = input("\nVuoi creare anche la cartella output/timmy-kb-dummy/repo per i test GitHub? [y/N]: ").strip().lower()
    if resp_repo == "y":
        if dummy_repo.exists():
            shutil.rmtree(dummy_repo)
        dummy_repo.mkdir(parents=True, exist_ok=True)
        (dummy_repo / "README.md").write_text("# Dummy Repo per test GitHub\n\nQuesta cartella viene usata per test automatici.", encoding="utf-8")
        (dummy_repo / "test.txt").write_text("File di test\n", encoding="utf-8")
        logger.info("✅ Cartella dummy_repo creata", extra={"file_path": str(dummy_repo)})
    else:
        logger.info("⏭️  Salto creazione cartella dummy_repo.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
