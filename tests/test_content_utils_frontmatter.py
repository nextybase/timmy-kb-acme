# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pipeline import content_utils as cu
from pipeline.exceptions import PipelineError
from semantic.config import SemanticConfig


def test_write_markdown_logs_frontmatter_read_failure(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture, tmp_path: Path
) -> None:
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
    monkeypatch.setattr(cu, "_extract_pdf_text", lambda *args, **kwargs: "contenuto pdf")

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


def test_build_chunk_records_fallback_on_expected_frontmatter_error(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    md_path = tmp_path / "doc.md"
    md_path.write_text("# Titolo\n\ncontenuto", encoding="utf-8")

    def _raise_value_error(*_: object, **__: object) -> tuple[dict[str, object], str]:
        raise ValueError("frontmatter invalido")

    monkeypatch.setattr(cu, "read_frontmatter", _raise_value_error)

    records = cu.build_chunk_records_from_markdown_files(
        "dummy",
        [md_path],
        perimeter_root=tmp_path,
    )

    assert len(records) == 1
    assert records[0]["text"] == "# Titolo\n\ncontenuto"


def test_build_chunk_records_raises_on_unexpected_frontmatter_error(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    md_path = tmp_path / "doc.md"
    md_path.write_text("# Titolo\n\ncontenuto", encoding="utf-8")

    def _raise_runtime_error(*_: object, **__: object) -> tuple[dict[str, object], str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(cu, "read_frontmatter", _raise_runtime_error)

    with pytest.raises(RuntimeError, match="boom"):
        cu.build_chunk_records_from_markdown_files(
            "dummy",
            [md_path],
            perimeter_root=tmp_path,
        )


def test_build_chunk_records_raises_on_unicode_frontmatter_error(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    md_path = tmp_path / "doc.md"
    md_path.write_text("# Titolo\n\ncontenuto", encoding="utf-8")

    def _raise_unicode_error(*_: object, **__: object) -> tuple[dict[str, object], str]:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(cu, "read_frontmatter", _raise_unicode_error)

    with pytest.raises(UnicodeDecodeError):
        cu.build_chunk_records_from_markdown_files(
            "dummy",
            [md_path],
            perimeter_root=tmp_path,
        )


def test_build_chunk_records_fallback_on_frontmatter_pipeline_error(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    md_path = tmp_path / "doc.md"
    md_path.write_text("# Titolo\n\ncontenuto", encoding="utf-8")

    def _raise_pipeline_frontmatter(*_: object, **__: object) -> tuple[dict[str, object], str]:
        raise PipelineError("frontmatter corrupted")

    monkeypatch.setattr(cu, "read_frontmatter", _raise_pipeline_frontmatter)

    records = cu.build_chunk_records_from_markdown_files(
        "dummy",
        [md_path],
        perimeter_root=tmp_path,
    )

    assert len(records) == 1
    assert records[0]["text"] == "# Titolo\n\ncontenuto"


def test_build_chunk_records_raises_on_non_frontmatter_pipeline_error(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    md_path = tmp_path / "doc.md"
    md_path.write_text("# Titolo\n\ncontenuto", encoding="utf-8")

    def _raise_pipeline_non_frontmatter(*_: object, **__: object) -> tuple[dict[str, object], str]:
        raise PipelineError("db unavailable")

    monkeypatch.setattr(cu, "read_frontmatter", _raise_pipeline_non_frontmatter)

    with pytest.raises(PipelineError, match="db unavailable"):
        cu.build_chunk_records_from_markdown_files(
            "dummy",
            [md_path],
            perimeter_root=tmp_path,
        )
