# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_convert_passes_safe_pdfs.py
import logging

from pipeline.file_utils import safe_write_text
from semantic import convert_service
from tests.support.contexts import TestClientCtx


def test_convert_markdown_passes_safe_pdfs_when_supported(tmp_path, monkeypatch, caplog):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    normalized = base / "normalized"
    raw.mkdir(parents=True)
    book.mkdir(parents=True)
    normalized.mkdir(parents=True)
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    safe_write_text(normalized / "doc.md", "# Doc\n\nBody\n", encoding="utf-8", atomic=True)
    safe_write_text(book / "README.md", "# KB\n", encoding="utf-8", atomic=True)
    safe_write_text(book / "SUMMARY.md", "# Summary\n", encoding="utf-8", atomic=True)

    ctx = TestClientCtx(
        slug="dummy",
        repo_root_dir=base,
        semantic_dir=base / "semantic",
        config_dir=base / "config",
    )

    caplog.set_level(logging.INFO)
    out = convert_service.convert_markdown(ctx, logging.getLogger("test"), slug="dummy")

    assert out == [book / "doc.md"]
