from pathlib import Path
import pytest
from src.onboarding_full import _book_md_only_guard
from pipeline.exceptions import PushError

def test_book_guard_accepts_md_and_ignores_md_fp(tmp_path: Path):
    base_dir = tmp_path / "output" / "timmy-kb-test"
    book = base_dir / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "ok.md").write_text("# ok\n", encoding="utf-8")
    (book / "placeholder.md.fp").write_text("", encoding="utf-8")

    md_files = _book_md_only_guard(base_dir, logger=_DummyLogger())
    assert len(md_files) == 1
    assert md_files[0].name == "ok.md"

def test_book_guard_raises_on_non_md(tmp_path: Path):
    base_dir = tmp_path / "output" / "timmy-kb-test"
    book = base_dir / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "ok.md").write_text("# ok\n", encoding="utf-8")
    (book / "image.png").write_bytes(b"\x89PNG")

    with pytest.raises(PushError):
        _book_md_only_guard(base_dir, logger=_DummyLogger())

class _DummyLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
