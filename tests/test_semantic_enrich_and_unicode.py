from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

import semantic.semantic_extractor as se


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj") -> None:
        self.base_dir = base
        self.md_dir = base / "book"
        self.slug = slug
        self.enrich_enabled = True


def test_term_pattern_matches_with_zero_width_removed() -> None:
    kw = "nome"
    content_zw = "no\u200Cme e no\u200Bme"
    pat = se._term_to_pattern(kw)
    import re as _re

    norm_content = _re.sub(r"[\u200B\u200C\u200D\uFEFF]", "", content_zw).lower()
    assert pat.search(norm_content) is not None


def test_enrich_markdown_folder_disabled_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\nBody\n", encoding="utf-8")

    ctx = _Ctx(base)
    ctx.enrich_enabled = False

    logger = logging.getLogger("test.enrich")
    with caplog.at_level(logging.INFO):
        se.enrich_markdown_folder(ctx, logger)

    assert any("enrich.disabled" in r.getMessage() for r in caplog.records)


def test_enrich_markdown_folder_invokes_hook(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\nBody\n", encoding="utf-8")
    (book / "b.md").write_text("# B\nBody\n", encoding="utf-8")

    called: list[str] = []

    def _spy(ctx: Any, file: Path, logger: logging.Logger) -> None:
        called.append(file.name)

    monkeypatch.setattr(se, "_enrich_md", _spy)
    se.enrich_markdown_folder(_Ctx(base), logging.getLogger("test.enrich2"))

    assert set(called) == {"a.md", "b.md"}
