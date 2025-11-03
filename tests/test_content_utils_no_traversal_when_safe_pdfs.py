# SPDX-License-Identifier: GPL-3.0-only
# tests/test_content_utils_no_traversal_when_safe_pdfs.py
from pathlib import Path
from types import SimpleNamespace

import timmykb.pipeline.content_utils as cu


def _ctx(base: Path, raw: Path, book: Path):
    return SimpleNamespace(base_dir=base, raw_dir=raw, md_dir=book, slug="dummy")


def test_convert_md_uses_safe_pdfs_without_traversal(monkeypatch, tmp_path):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)

    # PDF reali (anche annidati)
    root_pdf = raw / "root.pdf"
    cat1 = raw / "cat1"
    cat2 = raw / "cat2"
    sub = cat1 / "sub"
    cat1.mkdir(parents=True, exist_ok=True)
    cat2.mkdir(parents=True, exist_ok=True)
    sub.mkdir(parents=True, exist_ok=True)

    (cat1 / "doc1.pdf").write_text("pdf1", encoding="utf-8")
    (cat2 / "doc2.pdf").write_text("pdf2", encoding="utf-8")
    (sub / "deep.pdf").write_text("pdf3", encoding="utf-8")
    root_pdf.write_text("pdf0", encoding="utf-8")

    # Lista safe_pdfs (già validati/risolti)
    safe_pdfs = [
        root_pdf.resolve(),
        (cat1 / "doc1.pdf").resolve(),
        (cat2 / "doc2.pdf").resolve(),
        (sub / "deep.pdf").resolve(),
    ]

    # Orfano pre-esistente che dovrà essere pulito dal cleanup idempotente
    orphan = book / "orphan.md"
    orphan.write_text("# Old\n", encoding="utf-8")

    # Se il codice provasse a usare i percorsi legacy, falliamo il test
    def boom(*_a, **_k):  # pragma: no cover - vogliamo che NON venga mai chiamato
        raise AssertionError("legacy traversal used")

    monkeypatch.setattr(cu, "_iter_category_pdfs", boom)
    monkeypatch.setattr(cu, "_filter_safe_pdfs", boom)

    # Esegue la conversione passando safe_pdfs (niente traversal legacy)
    ctx = _ctx(base, raw, book)
    cu.convert_files_to_structured_markdown(ctx, md_dir=book, safe_pdfs=safe_pdfs)

    # File attesi:
    # - raw.md (per i PDF in root/)
    # - cat1.md, cat2.md (categorie immediate)
    expected = {book / "raw.md", book / "cat1.md", book / "cat2.md"}
    produced = set(book.glob("*.md")) - {book / "README.md", book / "SUMMARY.md"}
    assert expected.issubset(produced)

    # L'orphan deve essere stato rimosso
    assert not orphan.exists()

    # Contenuti basilari attesi (titoli e sezioni)
    assert "# Raw" in (book / "raw.md").read_text(encoding="utf-8")
    cat1_txt = (book / "cat1.md").read_text(encoding="utf-8")
    assert "# Cat1" in cat1_txt
    assert "doc1.pdf" in cat1_txt  # riferimento al file
    # Presenza di heading per sottocartella "sub" (capitalizzata)
    assert "## Sub" in cat1_txt or "### Sub" in cat1_txt

    # Idempotenza: seconda esecuzione non cambia i file generati e non esplora legacy
    cu.convert_files_to_structured_markdown(ctx, md_dir=book, safe_pdfs=safe_pdfs)
    produced2 = set(book.glob("*.md")) - {book / "README.md", book / "SUMMARY.md"}
    assert produced2 == produced
