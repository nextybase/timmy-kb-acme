# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import PipelineError
from semantic.entities_extractor import DocEntityHit
from semantic.entities_runner import run_doc_entities_pipeline


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo_root_dir = tmp_path / "repo"
    raw_dir = repo_root_dir / "raw"
    semantic_dir = repo_root_dir / "semantic"
    db_path = semantic_dir / "tags.db"
    raw_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "a.pdf").write_bytes(b"%PDF-1.4\n%")
    return repo_root_dir, raw_dir, semantic_dir, db_path


def _patch_success_primitives(monkeypatch: pytest.MonkeyPatch, *, persist_raises: bool = False) -> dict[str, int]:
    saved = {"count": 0}
    monkeypatch.setattr(
        "semantic.entities_runner.load_semantic_config",
        lambda *_a, **_k: SimpleNamespace(mapping={"k": "v"}, spacy_model="it_core_news_sm", slug="dummy"),
    )
    monkeypatch.setattr("semantic.entities_runner.build_lexicon", lambda _mapping: ["entry"])
    monkeypatch.setattr("semantic.entities_runner.build_lexicon_map", lambda _entries: {"ops": {"entity": object()}})
    monkeypatch.setattr("semantic.entities_runner._load_spacy", lambda _model: (lambda text: text))
    monkeypatch.setattr("semantic.entities_runner.make_phrase_matcher", lambda _nlp, _lex: object())
    monkeypatch.setattr("semantic.entities_runner._read_document_text", lambda _p: "testo")
    monkeypatch.setattr(
        "semantic.entities_runner.extract_doc_entities",
        lambda doc_uid, _doc, _matcher: [
            DocEntityHit(doc_uid=doc_uid, area_key="ops", entity_id="entity", span=None, confidence=0.9)
        ],
    )
    monkeypatch.setattr("semantic.entities_runner.reduce_doc_entities", lambda hits, **_k: list(hits))

    def _save(_db: Path, records: list[object]) -> None:
        if persist_raises:
            raise OSError("boom-save")
        saved["count"] = len(records)

    monkeypatch.setattr("semantic.entities_runner.save_doc_entities", _save)
    return saved


def test_run_doc_entities_pipeline_hard_fails_on_spacy_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root_dir, raw_dir, semantic_dir, db_path = _paths(tmp_path)
    _patch_success_primitives(monkeypatch)
    monkeypatch.setattr("semantic.entities_runner._load_spacy", lambda _model: (_ for _ in ()).throw(RuntimeError("x")))

    with pytest.raises(PipelineError, match="entities.spacy.load failed for slug=dummy"):
        run_doc_entities_pipeline(
            repo_root_dir=repo_root_dir,
            raw_dir=raw_dir,
            semantic_dir=semantic_dir,
            db_path=db_path,
            slug="dummy",
        )


def test_run_doc_entities_pipeline_hard_fails_on_persist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root_dir, raw_dir, semantic_dir, db_path = _paths(tmp_path)
    _patch_success_primitives(monkeypatch, persist_raises=True)

    with pytest.raises(PipelineError, match="entities.persist failed for slug=dummy"):
        run_doc_entities_pipeline(
            repo_root_dir=repo_root_dir,
            raw_dir=raw_dir,
            semantic_dir=semantic_dir,
            db_path=db_path,
            slug="dummy",
        )


def test_run_doc_entities_pipeline_ok_without_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root_dir, raw_dir, semantic_dir, db_path = _paths(tmp_path)
    saved = _patch_success_primitives(monkeypatch)

    result = run_doc_entities_pipeline(
        repo_root_dir=repo_root_dir,
        raw_dir=raw_dir,
        semantic_dir=semantic_dir,
        db_path=db_path,
        slug="dummy",
    )

    assert saved["count"] > 0
    assert result["entities_written"] > 0
    assert result["processed_pdfs"] == 1
    assert "skipped" not in result
