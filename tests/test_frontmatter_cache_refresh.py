# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

from pipeline import content_utils as cu
from semantic.config import SemanticConfig


def test_frontmatter_cache_updates_after_write(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    target_root = tmp_path / "book"
    raw_root.mkdir()
    target_root.mkdir()

    pdf_path = raw_root / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%")

    cu.clear_frontmatter_cache()

    # Prima scrittura con tag A
    cu._write_markdown_for_pdf(  # noqa: SLF001
        pdf_path,
        raw_root,
        target_root,
        candidates={"doc.pdf": {"tags": ["A"]}},
        cfg=SemanticConfig(),
        slug=None,
    )

    # Seconda scrittura con tag B (stessa cache key aggiornata)
    cu._write_markdown_for_pdf(  # noqa: SLF001
        pdf_path,
        raw_root,
        target_root,
        candidates={"doc.pdf": {"tags": ["B"]}},
        cfg=SemanticConfig(),
        slug=None,
    )

    # Recupera l'entry appena scritta dalla cache
    stat = (target_root / "doc.md").stat()
    cache_key = ((target_root / "doc.md"), stat.st_mtime_ns, stat.st_size)
    meta, body = cu._FRONTMATTER_CACHE[cache_key]  # noqa: SLF001

    assert meta["tags_raw"] == ["B"]
    assert "Documento sincronizzato" in body
