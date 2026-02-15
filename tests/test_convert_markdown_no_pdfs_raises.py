# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_convert_markdown_no_pdfs_raises.py
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from semantic import convert_service
from tests._helpers.noop_logger import NoopLogger


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.repo_root_dir = base
        self.base_dir = base
        self.normalized_dir = base / "normalized"
        self.book_dir = base / "book"
        self.slug = slug


def test_convert_markdown_without_pdfs_raises_configerror(tmp_path: Path):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = NoopLogger()

    # Layout minimo richiesto dal WorkspaceLayout (bootstrap-like)
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: dummy\n", encoding="utf-8")
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "book" / "README.md").write_text("# Placeholder\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Placeholder\n", encoding="utf-8")

    # normalized/ vuota e BOOK senza contenuti aggiuntivi
    (ctx.normalized_dir / "foo").mkdir(parents=True, exist_ok=True)

    with pytest.raises(ConfigError) as ei:
        convert_service.convert_markdown(ctx, logger=logger, slug=ctx.slug)

    err = ei.value
    assert getattr(err, "slug", None) == ctx.slug
    assert Path(getattr(err, "file_path", "")) == ctx.normalized_dir


def test_convert_markdown_without_pdfs_returns_existing_book_md(tmp_path: Path):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = NoopLogger()

    # Layout minimo richiesto dal WorkspaceLayout (bootstrap-like)
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: dummy\n", encoding="utf-8")
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "book" / "README.md").write_text("# Placeholder\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Placeholder\n", encoding="utf-8")
    ctx.normalized_dir.mkdir(parents=True, exist_ok=True)

    # BOOK con un contenuto preesistente
    (ctx.book_dir / "foo.md").write_text("# Foo\n\n", encoding="utf-8")

    mds = convert_service.convert_markdown(ctx, logger=logger, slug=ctx.slug)
    names = {p.name for p in mds}
    assert "foo.md" in names
