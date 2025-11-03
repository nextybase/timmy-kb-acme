# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

from pipeline.content_utils import convert_files_to_structured_markdown
from tests.utils.symlink import make_symlink


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


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
    make_symlink(real, alias, is_dir=True)

    ctx = _Ctx(base)

    # Non deve alzare eccezioni e deve produrre un markdown di categoria
    convert_files_to_structured_markdown(ctx)

    # Il nome del file può riflettere il nome alias o real in base alla risoluzione; accettiamo entrambi
    alias_md = ctx.md_dir / "alias.md"
    real_md = ctx.md_dir / "real.md"
    assert alias_md.exists() or real_md.exists()
