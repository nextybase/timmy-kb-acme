# SPDX-License-Identifier: GPL-3.0-only
# tests/test_convert_markdown_rerun_processes_new_pdfs.py
from pathlib import Path

from semantic.api import convert_markdown


class _Ctx:
    def __init__(self, base: Path, slug: str = "dummy"):
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
    ctx = _Ctx(base, slug="dummy")
    logger = _NoopLogger()

    # Primo run: un PDF in raw/foo -> deve produrre book/foo/a.md
    _touch(ctx.raw_dir / "foo" / "a.pdf")
    mds_first = convert_markdown(ctx, logger=logger, slug="dummy")
    assert (ctx.md_dir / "foo" / "a.md").exists()
    assert any(p.relative_to(ctx.md_dir).as_posix() == "foo/a.md" for p in mds_first)

    # Secondo run: aggiungo un nuovo PDF in raw/bar -> deve produrre anche book/bar/b.md
    _touch(ctx.raw_dir / "bar" / "b.pdf")
    mds_second = convert_markdown(ctx, logger=logger, slug="dummy")
    assert (ctx.md_dir / "bar" / "b.md").exists()

    # I Markdown di contenuto devono includere entrambi (README/SUMMARY esclusi)
    names = {p.relative_to(ctx.md_dir).as_posix() for p in mds_second}
    assert {"foo/a.md", "bar/b.md"}.issubset(names)
