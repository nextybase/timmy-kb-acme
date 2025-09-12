import logging
from pathlib import Path


def _ctx(base_dir: Path):
    class C:
        pass

    c = C()
    c.base_dir = base_dir
    c.raw_dir = base_dir / "raw"
    c.md_dir = base_dir / "book"
    c.slug = "x"
    return c


def test_build_markdown_book_end_to_end(tmp_path):
    from semantic.api import build_markdown_book

    base = tmp_path / "output" / "timmy-kb-x"
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "HR").mkdir(exist_ok=True)
    (raw / "HR" / "Policy.pdf").write_bytes(b"%PDF-1.4\n")
    (raw / "Finance").mkdir(exist_ok=True)
    (raw / "Finance" / "Report2024.pdf").write_bytes(b"%PDF-1.4\n")

    mds = build_markdown_book(_ctx(base), logging.getLogger("test"), slug="x")
    # Deve generare almeno i 2 file per cartella
    names = {p.name for p in mds}
    assert "HR.md" in names and "Finance.md" in names
    # README/SUMMARY presenti in book/
    book = base / "book"
    assert (book / "README.md").exists()
    assert (book / "SUMMARY.md").exists()
