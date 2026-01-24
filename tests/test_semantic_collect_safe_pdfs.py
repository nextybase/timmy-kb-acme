# SPDX-License-Identifier: GPL-3.0-only
import logging

from semantic.convert_service import _collect_safe_markdown


def test_collect_only_markdown(tmp_path):
    logger = logging.getLogger("test.semantic.collect")

    md_path = tmp_path / "a.md"
    md_path.write_text("# A\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nope", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "c.md").write_text("# C\n", encoding="utf-8")

    safe, discarded = _collect_safe_markdown(tmp_path, logger=logger, slug="dummy")

    names = {path.name for path in safe}
    assert "a.md" in names
    assert "c.md" in names
    assert all(name.endswith(".md") for name in names)
    assert discarded >= 0
