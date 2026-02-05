# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_unit_build_tags_csv.py
import csv
import logging
import sqlite3
from pathlib import Path

import pytest

from pipeline.exceptions import PathTraversalError
from semantic.api import build_tags_csv
from storage.tags_store import derive_db_path_from_yaml_path, ensure_schema_v2
from tests._helpers.workspace_paths import local_workspace_dir
from tests.support.contexts import TestClientCtx


def test_build_tags_csv_generates_posix_paths_and_header(tmp_path: Path) -> None:
    slug = "dummy"
    base_root = tmp_path / "output"
    base_dir = local_workspace_dir(base_root, slug)
    normalized = base_dir / "normalized"
    raw_dir = base_dir / "raw"
    sem = base_dir / "semantic"
    book = base_dir / "book"
    config_dir = base_dir / "config"
    logs_dir = base_dir / "logs"

    normalized.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    sem.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    (sem / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    (book / "README.md").write_text("# README\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    ensure_schema_v2(str(sem / "tags.db"))

    nested = normalized / "HR" / "Policies"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "Welcome Packet 2024.md").write_text("# Welcome\n", encoding="utf-8")
    (normalized / "Security-Guide_v2.md").write_text("# Security\n", encoding="utf-8")

    context = TestClientCtx(
        slug=slug,
        repo_root_dir=base_dir,
        semantic_dir=sem,
        config_dir=config_dir,
    )
    csv_path = build_tags_csv(context, logging.getLogger("test"), slug=slug)

    assert csv_path == sem / "tags_raw.csv"
    assert csv_path.exists()
    readme_path = sem / "README_TAGGING.md"
    assert readme_path.exists()
    assert "Tag Onboarding (HiTL)" in readme_path.read_text(encoding="utf-8")

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert reader.fieldnames == [
        "relative_path",
        "suggested_tags",
        "entities",
        "keyphrases",
        "score",
        "sources",
    ]
    assert len(rows) == 2

    rel_paths = {r["relative_path"] for r in rows}
    assert "normalized/HR/Policies/Welcome Packet 2024.md" in rel_paths
    assert "normalized/Security-Guide_v2.md" in rel_paths


def test_build_tags_csv_rejects_tags_db_outside_semantic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "dummy"
    base_root = tmp_path / "output"
    base_dir = local_workspace_dir(base_root, slug)
    normalized = base_dir / "normalized"
    raw_dir = base_dir / "raw"
    sem = base_dir / "semantic"
    book = base_dir / "book"
    config_dir = base_dir / "config"
    logs_dir = base_dir / "logs"

    normalized.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    sem.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    (sem / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    (book / "README.md").write_text("# README\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    ensure_schema_v2(str(sem / "tags.db"))

    (normalized / "dummy.md").write_text("# Dummy\n", encoding="utf-8")

    context = TestClientCtx(
        slug=slug,
        repo_root_dir=base_dir,
        semantic_dir=sem,
        config_dir=config_dir,
    )

    monkeypatch.setattr(
        "semantic.tagging_service.derive_db_path_from_yaml_path",
        lambda yaml_path: base_dir.parent / "escape" / "tags.db",
    )

    with pytest.raises(PathTraversalError):
        build_tags_csv(context, logging.getLogger("test"), slug=slug)


def test_build_tags_csv_writes_doc_entities_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "dummy"
    base_root = tmp_path / "output"
    base_dir = local_workspace_dir(base_root, slug)
    normalized = base_dir / "normalized"
    raw_dir = base_dir / "raw"
    sem = base_dir / "semantic"
    book = base_dir / "book"
    config_dir = base_dir / "config"
    logs_dir = base_dir / "logs"

    normalized.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    sem.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    (sem / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    (book / "README.md").write_text("# README\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    ensure_schema_v2(str(sem / "tags.db"))

    def _fake_candidates(_normalized_dir: Path, _cfg: object) -> dict[str, dict[str, object]]:
        return {
            "normalized/Doc.md": {
                "tags": ["policy"],
                "sources": {"spacy": {"areas": {"compliance": ["GDPR"]}}},
                "score": {"compliance:GDPR": 0.9},
            }
        }

    monkeypatch.setattr("semantic.tagging_service.extract_semantic_candidates", _fake_candidates)

    context = TestClientCtx(
        slug=slug,
        repo_root_dir=base_dir,
        semantic_dir=sem,
        config_dir=config_dir,
    )
    build_tags_csv(context, logging.getLogger("test"), slug=slug)

    db_path = Path(derive_db_path_from_yaml_path(sem / "tags_reviewed.yaml"))
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM doc_entities").fetchone()
    assert row is not None and row[0] >= 1
