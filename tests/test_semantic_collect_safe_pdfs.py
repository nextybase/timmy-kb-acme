# SPDX-License-Identifier: GPL-3.0-only
import logging

from semantic.api import _collect_safe_pdfs


def test_collect_only_pdfs(tmp_path):
    logger = logging.getLogger("test.semantic.collect")

    pdf_path = tmp_path / "a.pdf"
    pdf_path.write_bytes(b"0")
    (tmp_path / "b.txt").write_text("nope", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "c.pdf").write_bytes(b"0")

    safe, discarded = _collect_safe_pdfs(tmp_path, logger=logger, slug="dummy")

    names = {path.name for path in safe}
    assert "a.pdf" in names
    assert "c.pdf" in names
    assert all(name.endswith(".pdf") for name in names)
    assert discarded >= 0
