# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from pathlib import Path

import pytest

import semantic.embedding_service as es


def test_collect_markdown_inputs_raises_on_unicode_decode_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    md_path = tmp_path / "doc.md"
    md_path.write_text("# Titolo\n\ncontenuto", encoding="utf-8")

    def _raise_unicode(*_: object, **__: object) -> tuple[dict[str, object], str]:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(es, "_read_fm", _raise_unicode, raising=True)

    with pytest.raises(UnicodeDecodeError):
        es._collect_markdown_inputs(
            tmp_path,
            [md_path],
            logging.getLogger("test.semantic.embedding.strict"),
            "dummy",
        )
