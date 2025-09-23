from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.content_utils import convert_files_to_structured_markdown


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


def _make_symlink(src: Path, dst: Path) -> None:
    try:
        dst.symlink_to(src, target_is_directory=True)
    except OSError as e:
        pytest.skip(f"symlink not supported on this platform: {e}")


def test_convert_structured_markdown_handles_symlink_category(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    real = raw / "real"
    sub = real / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    pdf = sub / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%\n")

    alias = raw / "alias"
    _make_symlink(real, alias)

    ctx = _Ctx(base)

    # Non deve alzare eccezioni e deve produrre un markdown di categoria
    convert_files_to_structured_markdown(ctx)

    # Il nome del file può riflettere il nome alias o real in base alla risoluzione; accettiamo entrambi
    alias_md = ctx.md_dir / "alias.md"
    real_md = ctx.md_dir / "real.md"
    assert alias_md.exists() or real_md.exists()
