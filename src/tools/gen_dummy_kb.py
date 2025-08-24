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
from pipeline.file_utils import ensure_within, safe_write_text  # ✅ PR-3: path guard + atomic write
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
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if FPDF is None:
        placeholder = out_path.with_suffix(".txt")
        text = f"# {titolo}\n\n" + "\n\n".join(paragrafi) + "\n"
        safe_write_text(placeholder, text, encoding="utf-8", atomic=True)  # ✅ atomico
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
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for cat in cartelle:
        cat_folder = raw_dir / cat
        # ✅ PR-3: path guard forte – deve stare sotto raw_dir
        try:
            ensure_within(raw_dir, cat_folder)
        except ConfigError:
            logger.debug("Skip (path non sicuro)", extra={"file_path": str(cat_folder)})
            continue

        cat_folder.mkdir(parents=True, exist_ok=True)
        info = pdf_dummy.get(cat, {})
        titolo = info.get("titolo", f"Sezione: {cat.title()}")
        paragrafi = info.get(
            "paragrafi",
            [
                "Questo è un paragrafo di esempio.",
                "Puoi personalizzare il contenuto dei PDF modificando pdf_dummy.yaml.",
                "Sezione tematica generica.",
            ],
        )
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

    # ✅ PR-3: path-safety (base deve vivere sotto il repo)
    try:
        ensure_within(project_root, base)
    except ConfigError:
        logger.error("Base path non sicuro", extra={"file_path": str(base)})
        return EXIT_CODES.get("ConfigError", 2)

    # 1) Crea cartelle principali
    for folder in (book, config_dir, raw, dummy_repo):
        folder.mkdir(parents=True, exist_ok=True)

    # 2) Crea README/SUMMARY/test nel book (scritture atomiche)
    try:
        ensure_within(book, book / "README.md")
        ensure_within(book, book / "SUMMARY.md")
        ensure_within(book, book / "test.md")
    except ConfigError as e:
        logger.error(str(e))
        return EXIT_CODES.get("ConfigError", 2)

    safe_write_text(
        book / "README.md",
        "# Dummy KB – Test\n\nQuesta è una knowledge base di test generata automaticamente.\n",
        encoding="utf-8",
        atomic=True,
    )
    safe_write_text(
        book / "SUMMARY.md",
        "# Sommario\n\n* [Introduzione](README.md)\n* [Test Markdown](test.md)\n",
        encoding="utf-8",
        atomic=True,
    )
    safe_write_text(
        book / "test.md",
        "# Test Markdown\n\nQuesto è un file markdown di esempio per testare la pipeline Honkit.\n- Punto uno\n- Punto due\n",
        encoding="utf-8",
        atomic=True,
    )

    # 3) Crea config.yaml minimale (atomico)
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
    try:
        ensure_within(config_dir, config_dir / "config.yaml")
    except ConfigError as e:
        logger.error(str(e))
        return EXIT_CODES.get("ConfigError", 2)

    import yaml
    yaml_text = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    safe_write_text(config_dir / "config.yaml", yaml_text, encoding="utf-8", atomic=True)

    logger.info("✅ Cartella base KB generata", extra={"base": str(base)})

    # 4) Genera RAW da YAML + PDF
    raw_yaml = project_root / RAW_YAML_REL
    pdf_yaml = project_root / PDF_YAML_REL
    # path-safety per gli YAML di input (devono stare nel repo)
    for p in (raw_yaml, pdf_yaml):
        if not is_safe_subpath(p, project_root):
            logger.error("YAML fuori dal repo: abort", extra={"file_path": str(p)})
            return EXIT_CODES.get("ConfigError", 2)
    genera_raw_structure(raw, raw_yaml, pdf_yaml)

    # 5) Opzionale: crea cartella repo di test (interattivo, default NO)
    resp_repo = input("\nVuoi creare anche la cartella output/timmy-kb-dummy/repo per i test GitHub? [y/N]: ").strip().lower()
    if resp_repo == "y":
        if dummy_repo.exists():
            shutil.rmtree(dummy_repo)
        dummy_repo.mkdir(parents=True, exist_ok=True)
        try:
            ensure_within(dummy_repo, dummy_repo / "README.md")
            ensure_within(dummy_repo, dummy_repo / "test.txt")
        except ConfigError as e:
            logger.error(str(e))
            return EXIT_CODES.get("ConfigError", 2)

        safe_write_text(
            dummy_repo / "README.md",
            "# Dummy Repo per test GitHub\n\nQuesta cartella viene usata per test automatici.",
            encoding="utf-8",
            atomic=True,
        )
        safe_write_text(dummy_repo / "test.txt", "File di test\n", encoding="utf-8", atomic=True)
        logger.info("✅ Cartella dummy_repo creata", extra={"file_path": str(dummy_repo)})
    else:
        logger.info("⏭️  Salto creazione cartella dummy_repo.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
