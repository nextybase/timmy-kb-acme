# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_content_utils_no_traversal_when_safe_pdfs.py
from dataclasses import dataclass, field
from pathlib import Path

import pipeline.content_utils as cu
from pipeline.workspace_layout import WorkspaceLayout


@dataclass
class _LayoutCtx:
    slug: str
    repo_root_dir: Path
    _layout: WorkspaceLayout = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._layout = WorkspaceLayout.from_context(self)

    @property
    def raw_dir(self) -> Path:
        return self._layout.raw_dir

    @property
    def book_dir(self) -> Path:
        return self._layout.book_dir


def _ctx(base: Path) -> _LayoutCtx:
    return _LayoutCtx(slug="dummy", repo_root_dir=base)


def test_convert_md_uses_safe_pdfs_without_traversal(monkeypatch, tmp_path):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    semantic_dir = base / "semantic"
    normalized_dir = base / "normalized"
    config_dir = base / "config"
    logs_dir = base / "logs"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    (semantic_dir / "semantic_mapping.yaml").write_text("areas: {}\n", encoding="utf-8")
    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    (book / "README.md").write_text("# README\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")

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
    # Lista safe_pdfs (gia validati/risolti)
    safe_pdfs = [
        root_pdf.resolve(),
        (cat1 / "doc1.pdf").resolve(),
        (cat2 / "doc2.pdf").resolve(),
        (sub / "deep.pdf").resolve(),
    ]
    # Orfano pre-esistente che dovra essere pulito dal cleanup idempotente
    orphan = book / "orphan.md"
    orphan.write_text("# Old\n", encoding="utf-8")

    # Se il codice provasse a usare i percorsi legacy, falliamo il test
    def boom(*_a, **_k):  # pragma: no cover - vogliamo che NON venga mai chiamato
        raise AssertionError("legacy traversal used")

    monkeypatch.setattr(cu, "_iter_category_pdfs", boom)
    monkeypatch.setattr(cu, "_extract_pdf_text", lambda *args, **kwargs: "contenuto pdf")

    # Esegue la conversione passando safe_pdfs (niente traversal legacy)
    ctx = _ctx(base)
    cu.convert_files_to_structured_markdown(ctx, book_dir=book, safe_pdfs=safe_pdfs)

    # File attesi: un markdown per ogni PDF (stessa struttura delle cartelle raw/)
    expected = {
        book / "root.md",
        book / "cat1" / "doc1.md",
        book / "cat2" / "doc2.md",
        book / "cat1" / "sub" / "deep.md",
    }
    produced = set(book.rglob("*.md")) - {book / "README.md", book / "SUMMARY.md"}
    assert expected.issubset(produced)

    # L'orphan deve essere stato rimosso
    assert not orphan.exists()

    # Contenuti basilari attesi (frontmatter + riferimenti al PDF)
    root_txt = (book / "root.md").read_text(encoding="utf-8")
    assert "source_file: root.pdf" in root_txt
    cat1_txt = (book / "cat1" / "doc1.md").read_text(encoding="utf-8")
    assert "tags_raw" in cat1_txt
    assert "doc1.pdf" in cat1_txt  # riferimento al file
    # Presenza del file annidato
    deep_txt = (book / "cat1" / "sub" / "deep.md").read_text(encoding="utf-8")
    assert "deep.pdf" in deep_txt

    # Idempotenza: seconda esecuzione non cambia i file generati e non esplora legacy
    cu.convert_files_to_structured_markdown(ctx, book_dir=book, safe_pdfs=safe_pdfs)
    produced2 = set(book.rglob("*.md")) - {book / "README.md", book / "SUMMARY.md"}
    assert produced2 == produced
