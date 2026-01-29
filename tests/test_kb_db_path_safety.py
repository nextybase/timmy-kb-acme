# SPDX-License-Identifier: GPL-3.0-only

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from storage.kb_db import insert_chunks


def test_db_rejects_legacy_global_data_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "semantic").mkdir(parents=True, exist_ok=True)

    with pytest.raises(ConfigError):
        insert_chunks(
            slug="obs",
            scope="s",
            path="p",
            version="v",
            meta_dict={},
            chunks=["c1"],
            embeddings=[[1.0]],
            db_path=Path("data") / "kb.sqlite",
        )
