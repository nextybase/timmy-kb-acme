# tests/test_convert_markdown_rerun_processes_new_pdfs.py
from pathlib import Path

from semantic.api import convert_markdown


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


class _NoopLogger:
    def info(self, *a, **k):  # noqa: D401
        """No-op."""
        pass

    def warning(self, *a, **k):  # noqa: D401
        """No-op."""
        pass

    def debug(self, *a, **k):  # noqa: D401
        """No-op."""
        pass

    def error(self, *a, **k):  # noqa: D401
        """No-op."""
        pass


def _touch(pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\n%dummy\n")  # contenuto minimale


def test_convert_markdown_rerun_processes_new_pdfs(tmp_path: Path):
    base = tmp_path / "kb"
    ctx = _Ctx(base, slug="proj")
    logger = _NoopLogger()

    # Primo run: un PDF in raw/foo → deve produrre book/foo.md
    _touch(ctx.raw_dir / "foo" / "a.pdf")
    mds_first = convert_markdown(ctx, logger=logger, slug="proj")
    assert (ctx.md_dir / "foo.md").exists()
    assert any(p.name == "foo.md" for p in mds_first)

    # Secondo run: aggiungo un nuovo PDF in raw/bar → deve produrre anche book/bar.md
    _touch(ctx.raw_dir / "bar" / "b.pdf")
    mds_second = convert_markdown(ctx, logger=logger, slug="proj")
    assert (ctx.md_dir / "bar.md").exists()

    # I Markdown di contenuto devono includere entrambi (README/SUMMARY esclusi)
    names = {p.name for p in mds_second}
    assert {"foo.md", "bar.md"}.issubset(names)
