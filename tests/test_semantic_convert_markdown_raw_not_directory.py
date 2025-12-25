# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_convert_markdown_raw_not_directory.py
import logging

import pytest
from tests.support.contexts import TestClientCtx

from semantic.api import ConfigError, convert_markdown


def test_convert_markdown_raw_not_directory_raises(tmp_path, caplog):
    base = tmp_path
    raw = base / "raw"  # file, non directory
    raw.write_text("not a dir", encoding="utf-8")
    book = base / "book"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    book.mkdir(parents=True, exist_ok=True)
    (book / "README.md").write_text("# KB\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")

    ctx = TestClientCtx(
        slug="dummy",
        base_dir=base,
        repo_root_dir=base,
        raw_dir=raw,
        md_dir=book,
        semantic_dir=base / "semantic",
        config_dir=base / "config",
    )
    ctx.repo_root_dir = base
    logger = logging.getLogger("test.convert_markdown")
    caplog.set_level(logging.INFO)

    with pytest.raises(ConfigError) as exc:
        convert_markdown(ctx, logger, slug="dummy")

    msg = str(exc.value)
    assert "raw" in msg.lower() and "directory" in msg.lower()
