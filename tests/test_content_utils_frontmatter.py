# SPDX-License-Identifier: GPL-3.0-only
import logging
from pathlib import Path

from pipeline import content_utils as cu
from pipeline.exceptions import PipelineError
from semantic.config import SemanticConfig


def test_write_markdown_logs_frontmatter_read_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    target_root = tmp_path / "book"
    raw_root.mkdir()
    target_root.mkdir()

    pdf_path = raw_root / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%")  # contenuto minimo per path/slug
    md_path = target_root / "doc.md"
    md_path.write_text("invalid frontmatter", encoding="utf-8")

    def _raise_frontmatter(*_: object, **__: object) -> tuple[dict[str, str], str]:
        raise PipelineError("frontmatter corrupted")

    monkeypatch.setattr(cu, "read_frontmatter", _raise_frontmatter)

    caplog.set_level(logging.WARNING)

    result = cu._write_markdown_for_pdf(  # noqa: SLF001
        pdf_path,
        raw_root,
        target_root,
        candidates={},
        cfg=SemanticConfig(),
        slug=None,
    )

    assert result == md_path
    content = md_path.read_text(encoding="utf-8")
    assert "source_file" in content
    assert any("pipeline.content.frontmatter_read_failed" in record.message for record in caplog.records), caplog.text
