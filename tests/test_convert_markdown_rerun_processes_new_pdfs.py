# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_convert_markdown_rerun_processes_new_pdfs.py
from pathlib import Path

from semantic.convert_service import convert_markdown


class _Ctx:
    def __init__(self, base: Path, slug: str = "dummy"):
        self.repo_root_dir = base
        self.base_dir = base
        self.normalized_dir = base / "normalized"
        self.book_dir = base / "book"
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


def _touch(md_path: Path) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("# Dummy\n", encoding="utf-8")


def test_convert_markdown_rerun_processes_new_pdfs(monkeypatch, tmp_path: Path):
    base = tmp_path / "kb"
    ctx = _Ctx(base, slug="dummy")
    logger = _NoopLogger()

    # Layout minimo richiesto dal WorkspaceLayout (bootstrap-like)
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: dummy\n", encoding="utf-8")
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "book" / "README.md").write_text("# Placeholder\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Placeholder\n", encoding="utf-8")
    # Primo run: un Markdown in normalized/foo -> deve produrre book/foo/a.md
    _touch(ctx.normalized_dir / "foo" / "a.md")
    mds_first = convert_markdown(ctx, logger=logger, slug="dummy")
    assert (ctx.book_dir / "foo" / "a.md").exists()
    assert any(p.relative_to(ctx.book_dir).as_posix() == "foo/a.md" for p in mds_first)

    # Secondo run: aggiungo un nuovo Markdown in normalized/bar -> deve produrre anche book/bar/b.md
    _touch(ctx.normalized_dir / "bar" / "b.md")
    mds_second = convert_markdown(ctx, logger=logger, slug="dummy")
    assert (ctx.book_dir / "bar" / "b.md").exists()

    # I Markdown di contenuto devono includere entrambi (README/SUMMARY esclusi)
    names = {p.relative_to(ctx.book_dir).as_posix() for p in mds_second}
    assert {"foo/a.md", "bar/b.md"}.issubset(names)
