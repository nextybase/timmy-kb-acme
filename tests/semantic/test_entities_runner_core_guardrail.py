# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from semantic.entities_runner import run_doc_entities_pipeline


def test_entities_strict_no_pdfs_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "tags.db"

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    monkeypatch.setenv("TAGS_NLP_BACKEND", "spacy")

    with pytest.raises(ConfigError):
        run_doc_entities_pipeline(
            slug="acme",
            semantic_dir=semantic_dir,
            raw_dir=raw_dir,
            db_path=db_path,
            repo_root_dir=tmp_path,
        )


def test_entities_strict_backend_not_supported_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "tags.db"

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    monkeypatch.setenv("TAGS_NLP_BACKEND", "unsupported-backend")

    with pytest.raises(ConfigError):
        run_doc_entities_pipeline(
            slug="acme",
            semantic_dir=semantic_dir,
            raw_dir=raw_dir,
            db_path=db_path,
            repo_root_dir=tmp_path,
        )
