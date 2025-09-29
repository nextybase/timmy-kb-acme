# tests/test_semantic_convert_markdown_raw_not_directory.py
import logging
from types import SimpleNamespace

import pytest

from src.semantic.api import ConfigError, convert_markdown


def test_convert_markdown_raw_not_directory_raises(tmp_path, caplog):
    base = tmp_path
    raw = base / "raw"  # file, non directory
    raw.write_text("not a dir", encoding="utf-8")
    book = base / "book"

    ctx = SimpleNamespace(base_dir=base, raw_dir=raw, md_dir=book)
    logger = logging.getLogger("test.convert_markdown")
    caplog.set_level(logging.INFO)

    with pytest.raises(ConfigError) as exc:
        convert_markdown(ctx, logger, slug="acme")

    assert "non è una directory" in str(exc.value)
