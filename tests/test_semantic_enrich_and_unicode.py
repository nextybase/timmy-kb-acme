# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

import semantic.core as se
from tests.utils.workspace import ensure_minimal_workspace_layout


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj") -> None:
        self.repo_root_dir = base
        self.base_dir = base
        self.book_dir = base / "book"
        self.slug = slug
        self.enrich_enabled = True


def test_term_pattern_matches_with_zero_width_removed() -> None:
    kw = "nome"
    content_zw = "no\u200cme e no\u200bme"
    pat = se._term_to_pattern(kw)
    import re as _re

    norm_content = _re.sub(r"[\u200B\u200C\u200D\uFEFF]", "", content_zw).lower()
    assert pat.search(norm_content) is not None


def test_enrich_markdown_folder_disabled_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = tmp_path / "kb"
    ensure_minimal_workspace_layout(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\nBody\n", encoding="utf-8")

    ctx = _Ctx(base)
    ctx.enrich_enabled = False

    logger = logging.getLogger("test.enrich")
    with caplog.at_level(logging.INFO):
        se.enrich_markdown_folder(ctx, logger)

    assert any("enrich.disabled" in r.getMessage() for r in caplog.records)


def test_enrich_markdown_folder_noop_when_disabled(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    ensure_minimal_workspace_layout(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\nBody\n", encoding="utf-8")

    ctx = _Ctx(base)
    ctx.enrich_enabled = False

    # Ensure no exception and files remain untouched (side-effect already limited)
    se.enrich_markdown_folder(ctx, logging.getLogger("test.enrich.disabled"))
    assert (book / "a.md").read_text(encoding="utf-8") == "# A\nBody\n"


def test_enrich_markdown_folder_invokes_hook(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    ensure_minimal_workspace_layout(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\nBody\n", encoding="utf-8")
    (book / "b.md").write_text("# B\nBody\n", encoding="utf-8")

    called: list[str] = []

    def _spy(ctx: Any, file: Path, logger: logging.Logger) -> None:
        called.append(file.name)

    monkeypatch.setattr(se, "_enrich_md", _spy)
    se.enrich_markdown_folder(_Ctx(base), logging.getLogger("test.enrich2"))

    assert set(called) == {"a.md", "b.md", "README.md", "SUMMARY.md"}


def test_extract_semantic_concepts_sanitizes_and_dedups_keywords(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "kb"
    ensure_minimal_workspace_layout(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "doc.md").write_text("# Titolo\nQuesto documento contiene il nome autore.\n", encoding="utf-8")

    ctx = _Ctx(base)

    # Mapping con alias che differiscono solo per zero-width
    mapping = {
        "persona": [
            "nome",
            "no\u200cme",  # con ZW non visibile
        ]
    }

    monkeypatch.setattr(se, "load_semantic_mapping", lambda context, logger=None: mapping)

    out = se.extract_semantic_concepts(ctx)
    assert set(out.keys()) == {"persona"}
    items = out["persona"]
    # Deve esserci un solo match e la keyword deve essere sanificata (nessun zero-width)
    assert len(items) == 1
    kw = items[0]["keyword"]
    assert kw == "nome"
    # Verifica esplicita: nessun char zero-width
    assert not any(ord(c) in {0x200B, 0x200C, 0x200D, 0xFEFF} for c in kw)
