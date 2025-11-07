# SPDX-License-Identifier: GPL-3.0-only
# tests/test_convert_markdown_no_pdfs_raises.py
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from semantic import api as sapi
from semantic import convert_service


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


def test_convert_markdown_without_pdfs_raises_configerror(tmp_path: Path, monkeypatch):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = _NoopLogger()

    # RAW con sole cartelle (vuote) e BOOK vuoto
    (ctx.raw_dir / "foo").mkdir(parents=True, exist_ok=True)
    ctx.md_dir.mkdir(parents=True, exist_ok=True)

    # Se non ci sono PDF, il converter NON deve essere chiamato: falliremmo qui
    monkeypatch.setattr(
        convert_service,
        "_call_convert_md",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("converter should NOT be called when RAW has no PDFs")),
    )

    with pytest.raises(ConfigError) as ei:
        sapi.convert_markdown(ctx, logger=logger, slug=ctx.slug)

    err = ei.value
    assert getattr(err, "slug", None) == ctx.slug
    assert Path(getattr(err, "file_path", "")) == ctx.raw_dir


def test_convert_markdown_without_pdfs_returns_existing_book_md(tmp_path: Path, monkeypatch):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = _NoopLogger()

    # RAW senza PDF
    ctx.raw_dir.mkdir(parents=True, exist_ok=True)
    # BOOK con un contenuto preesistente
    ctx.md_dir.mkdir(parents=True, exist_ok=True)
    (ctx.md_dir / "foo.md").write_text("# Foo\n\n", encoding="utf-8")

    # Il converter NON deve essere chiamato quando non ci sono PDF in RAW
    monkeypatch.setattr(
        convert_service,
        "_call_convert_md",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("converter should NOT be called when RAW has no PDFs")),
    )

    mds = sapi.convert_markdown(ctx, logger=logger, slug=ctx.slug)
    names = {p.name for p in mds}
    assert "foo.md" in names
