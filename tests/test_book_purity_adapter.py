# tests/test_book_purity_adapter.py
import logging
from pathlib import Path


def _ctx(base_dir: Path, md_sub: str = "book"):
    class Ctx:
        # Tipi dichiarati per soddisfare Pylance (attributi noti)
        slug: str
        base_dir: Path
        md_dir: Path

    c = Ctx()
    c.slug = "dummy"
    c.base_dir = base_dir
    c.md_dir = base_dir / md_sub
    return c


def test_book_purity_allows_md_and_placeholder(tmp_path):
    from adapters.book_purity import ensure_book_purity

    base = tmp_path / "out" / "timmy-kb-dummy"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "README.md").write_text("# ok")
    (book / "SUMMARY.md").write_text("# ok")
    (book / "note.md.fp").write_text("")

    ensure_book_purity(_ctx(base), logging.getLogger("test"))


def test_book_purity_allows_builder_and_ignores_caches(tmp_path):
    from adapters.book_purity import ensure_book_purity

    base = tmp_path / "out" / "timmy-kb-dummy"
    book = base / "book"
    (book / "_book").mkdir(parents=True, exist_ok=True)
    (book / "node_modules").mkdir(parents=True, exist_ok=True)
    (book / ".cache").mkdir(parents=True, exist_ok=True)
    (book / "book.json").write_text("{}")
    (book / "package.json").write_text("{}")
    (book / "README.md").write_text("# ok")

    ensure_book_purity(_ctx(base), logging.getLogger("test"))


def test_book_purity_raises_on_disallowed_files(tmp_path):
    import pytest

    from adapters.book_purity import ensure_book_purity

    base = tmp_path / "out" / "timmy-kb-dummy"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "bad.pdf").write_bytes(b"%PDF")
    (book / "misc").mkdir(parents=True, exist_ok=True)
    (book / "misc" / "file.bin").write_bytes(b"\x00\x01")

    with pytest.raises(Exception) as exc:
        ensure_book_purity(_ctx(base), logging.getLogger("test"))
    msg = str(exc.value)
    assert "bad.pdf" in msg and "misc/file.bin" in msg
