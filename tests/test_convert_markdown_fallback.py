from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import logging

import src.semantic.api as sapi


def test_convert_markdown_fallback_generates_md(tmp_path: Path) -> None:
    # Forza il fallback
    sapi._convert_md = None  # type: ignore[attr-defined]

    base = tmp_path / "output" / "timmy-kb-acme"
    raw = base / "raw"
    book = base / "book"
    (raw / "contratti_clienti").mkdir(parents=True)
    (raw / "note-tecniche").mkdir(parents=True)

    ctx = SimpleNamespace(base_dir=base, raw_dir=raw, md_dir=book)
    log = logging.getLogger("test")

    out = sapi.convert_markdown(ctx, log, slug="acme")

    # Due file generati con i nomi delle cartelle
    assert (book / "contratti_clienti.md").exists()
    assert (book / "note-tecniche.md").exists()

    # L'API restituisce una lista di Path relativi a book_dir (sorted)
    names = [p.name for p in out]
    assert "contratti_clienti.md" in names and "note-tecniche.md" in names

    # Contenuto placeholder atteso (titolo + riferimento alla cartella)
    text = (book / "contratti_clienti.md").read_text(encoding="utf-8")
    assert "# contratti clienti" in text.lower()
    assert "(Contenuti da contratti_clienti/)" in text
