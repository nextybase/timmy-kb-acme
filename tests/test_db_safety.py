# SPDX-License-Identifier: GPL-3.0-only

from pathlib import Path

import pytest

from kb_db import insert_chunks
from pipeline.exceptions import ConfigError


def test_db_default_requires_explicit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "semantic").mkdir(parents=True, exist_ok=True)

    with pytest.raises(ConfigError, match="db_path must be provided explicitly"):
        insert_chunks(
            slug="obs",
            scope="s",
            path="p",
            version="v",
            meta_dict={},
            chunks=["c1"],
            embeddings=[[1.0]],
            db_path=None,
        )


def test_db_default_missing_semantic_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="db_path must be provided explicitly"):
        insert_chunks(
            slug="obs",
            scope="s",
            path="p",
            version="v",
            meta_dict={},
            chunks=["c1"],
            embeddings=[[1.0]],
            db_path=None,
        )
