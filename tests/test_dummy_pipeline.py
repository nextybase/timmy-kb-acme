# tests/test_dummy_pipeline.py
from __future__ import annotations

from pathlib import Path
import csv
from typing import List, Optional

import pytest
from pydantic import BaseModel, Field, field_validator

# Import moduli semantic (conftest aggiunge la root del repo al sys.path)
from src.semantic.config import load_semantic_config
from src.semantic.auto_tagger import extract_semantic_candidates, render_tags_csv
from src.semantic.normalizer import normalize_tags


# -------------------------- Pydantic models ---------------------------------- #

class CsvRow(BaseModel):
    relative_path: str = Field(..., min_length=3)
    suggested_tags: str = Field(..., min_length=1)
    entities: Optional[str] = ""
    keyphrases: Optional[str] = ""
    score: Optional[str] = ""
    sources: Optional[str] = ""

    @field_validator("relative_path")
    @classmethod
    def must_be_posix(cls, v: str) -> str:
        # evitiamo backslash in CSV: i path devono essere POSIX relative
        assert "\\" not in v, f"path non POSIX nel CSV: {v}"
        assert not Path(v).is_absolute(), f"path assoluto non ammesso nel CSV: {v}"
        return v

    @property
    def tags_list(self) -> List[str]:
        return [t.strip() for t in self.suggested_tags.split(",") if t.strip()]


# ---------------------------- Helpers ---------------------------------------- #

def _read_csv_rows(csv_path: Path) -> List[CsvRow]:
    assert csv_path.exists(), f"CSV mancante: {csv_path}"
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [CsvRow(**row) for row in reader]
    assert rows, "CSV vuoto: attese righe per ciascun PDF rilevato"
    return rows

def _pdfs_under(base: Path) -> List[Path]:
    return sorted(p.relative_to(base) for p in (base).rglob("*.pdf"))

def _raw_pdfs(base: Path) -> List[Path]:
    raw = base / "raw"
    return sorted(p.relative_to(base) for p in raw.rglob("*.pdf"))


# ----------------------------- Tests ----------------------------------------- #
# Nota: la fixture `dummy_kb` (in conftest.py) genera la sandbox prima dei test.

def test_generate_dummy_structure(dummy_kb, base_dir: Path):
    # cartelle base
    for d in ("raw", "semantic", "config", "book", "logs"):
        assert (base_dir / d).exists(), f"Cartella mancante: {d}"
    # file semantic fondamentali
    assert (base_dir / "semantic" / "semantic_mapping.yaml").exists()
    assert (base_dir / "semantic" / "cartelle_raw.yaml").exists()
    # CSV generato dalla pipeline
    assert (base_dir / "semantic" / "tags_raw.csv").exists()

def test_semantic_csv_coherence_with_pdfs(dummy_kb, base_dir: Path):
    csv_path = base_dir / "semantic" / "tags_raw.csv"
    rows = _read_csv_rows(csv_path)
    row_paths = sorted(Path(r.relative_path) for r in rows)

    pdfs = _pdfs_under(base_dir)
    raw_only = _raw_pdfs(base_dir)

    # Nel dummy generiamo PDF solo sotto raw/
    assert set(pdfs) == set(raw_only), "Rilevati PDF fuori da raw/, non atteso nel dummy."

    # Cardinalità 1:1
    assert len(row_paths) == len(raw_only), f"Mismatch conteggio: CSV={len(row_paths)} vs PDF={len(raw_only)}"

    # Ogni riga del CSV deve puntare a un PDF presente
    missing_on_disk = sorted(set(row_paths) - set(raw_only))
    assert not missing_on_disk, f"Righe CSV senza corrispondenza PDF: {missing_on_disk}"

    # Tag minimi: ogni riga deve avere almeno 1 tag
    assert all(len(r.tags_list) >= 1 for r in rows), "Presente riga con suggested_tags vuoto."

def test_regenerate_csv_via_semantic_modules(dummy_kb, base_dir: Path):
    """
    Esegue i moduli semantic direttamente e verifica che il CSV risultante
    resti coerente con i PDF presenti (idempotenza della pipeline).
    """
    cfg = load_semantic_config(base_dir)
    candidates = extract_semantic_candidates(cfg.raw_dir, cfg)
    norm = normalize_tags(candidates, cfg.mapping)
    out = cfg.semantic_dir / "tags_raw.csv"
    render_tags_csv(norm, out)

    rows = _read_csv_rows(out)
    row_paths = sorted(Path(r.relative_path) for r in rows)
    raw_only = _raw_pdfs(base_dir)

    assert len(row_paths) == len(raw_only), "Dopo rigenerazione: mismatch conteggio CSV/PDF"
    assert set(row_paths) == set(raw_only), "Dopo rigenerazione: path nel CSV non corrispondono ai PDF"

def test_no_contrattualistica_local(dummy_kb, base_dir: Path):
    """Il dummy non deve creare 'contrattualistica/' locale."""
    assert not (base_dir / "contrattualistica").exists(), \
        "La cartella 'contrattualistica' non deve essere generata in locale per il dummy."
