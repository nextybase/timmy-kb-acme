# SPDX-License-Identifier: GPL-3.0-only

import importlib
import sys
import types

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.pipeline]

from pipeline.exceptions import ConfigError, PathTraversalError, PipelineError
from storage.tags_store import ensure_schema_v2, get_conn
from storage.tags_store import save_doc_terms as real_save_doc_terms
from storage.tags_store import upsert_document, upsert_folder
from tests.support.contexts import TestClientCtx
from timmy_kb.cli.tag_onboarding import _resolve_cli_paths, run_nlp_to_db, scan_normalized_to_db


def test_run_nlp_to_db_processes_nested_markdown(tmp_path, monkeypatch):
    normalized_dir = tmp_path / "normalized"
    md_dir = normalized_dir / "subdir"
    md_dir.mkdir(parents=True)
    md_path = md_dir / "dummy.md"
    md_path.write_text("dummy text", encoding="utf-8")

    db_path = tmp_path / "semantic" / "tags.db"
    ensure_schema_v2(str(db_path))

    with get_conn(str(db_path)) as conn:
        folder_id = upsert_folder(conn, "normalized/subdir", "normalized")
        doc_id = upsert_document(conn, folder_id, md_path.name, sha256="deadbeef", pages=1)

    captured_text: dict[str, str] = {}

    def fake_spacy_candidates(text: str, lang: str):
        captured_text["value"] = text
        return ["alpha"]

    monkeypatch.setattr("nlp.nlp_keywords.spacy_candidates", fake_spacy_candidates)
    monkeypatch.setattr("nlp.nlp_keywords.yake_scores", lambda text, top_k, lang: [("alpha", 0.9)])
    monkeypatch.setattr(
        "nlp.nlp_keywords.keybert_scores",
        lambda text, candidates, model_name, top_k: [("alpha", 0.8)],
    )
    monkeypatch.setattr("nlp.nlp_keywords.fuse_and_dedup", lambda text, cand_spa, sc_y, sc_kb: [("alpha", 0.7)])
    monkeypatch.setattr("nlp.nlp_keywords.topn_by_folder", lambda items, k: items[:k])
    monkeypatch.setattr("nlp.nlp_keywords.cluster_synonyms", lambda items, model_name, sim_thr: [])

    captured_doc_ids: list[int] = []
    captured_items: list[tuple[str, float, str]] = []

    def fake_save_doc_terms(conn, document_id, items):
        captured_doc_ids.append(document_id)
        captured_items.clear()
        captured_items.extend(items)
        return real_save_doc_terms(conn, document_id, items)

    monkeypatch.setattr("storage.tags_store.save_doc_terms", fake_save_doc_terms)

    # unit test isolation: skip entities pipeline to keep the NLP-only behavior deterministic.
    stats = run_nlp_to_db("dummy", normalized_dir, str(db_path), enable_entities=False)

    assert captured_text["value"] == "dummy text"
    assert captured_doc_ids == [doc_id]
    assert captured_items
    assert stats["doc_terms"] == len(captured_items)


def test_run_nlp_to_db_requires_repo_root_dir_in_strict(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir(parents=True)

    db_path = tmp_path / "semantic" / "tags.db"

    with pytest.raises(ConfigError):
        run_nlp_to_db("dummy", normalized_dir, str(db_path))


def test_run_nlp_to_db_records_entities_failure_non_strict(tmp_path, monkeypatch):
    monkeypatch.delenv("TIMMY_BETA_STRICT", raising=False)
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir(parents=True)
    db_path = tmp_path / "semantic" / "tags.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("semantic.nlp_runner.run_doc_terms_pipeline", lambda *_a, **_k: {"doc_terms": 0})

    fake_entities = types.ModuleType("semantic.entities_runner")

    def _boom(*_a, **_k):
        raise RuntimeError("entities failed")

    fake_entities.run_doc_entities_pipeline = _boom
    monkeypatch.setitem(sys.modules, "semantic.entities_runner", fake_entities)

    with pytest.raises(PipelineError):
        run_nlp_to_db("dummy", normalized_dir, str(db_path), repo_root_dir=tmp_path)


def test_run_nlp_to_db_entities_import_missing_non_strict(tmp_path, monkeypatch):
    monkeypatch.delenv("TIMMY_BETA_STRICT", raising=False)
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir(parents=True)
    db_path = tmp_path / "semantic" / "tags.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("semantic.nlp_runner.run_doc_terms_pipeline", lambda *_a, **_k: {"doc_terms": 0})

    original_import = importlib.import_module

    def _import_module(name: str, *args, **kwargs):
        if name == "semantic.entities_runner":
            raise ModuleNotFoundError("missing entities")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _import_module)

    with pytest.raises(PipelineError):
        run_nlp_to_db("dummy", normalized_dir, str(db_path), repo_root_dir=tmp_path)


def test_run_nlp_to_db_entities_import_missing_strict_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir(parents=True)
    db_path = tmp_path / "semantic" / "tags.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("semantic.nlp_runner.run_doc_terms_pipeline", lambda *_a, **_k: {"doc_terms": 0})

    original_import = importlib.import_module

    def _import_module(name: str, *args, **kwargs):
        if name == "semantic.entities_runner":
            raise ModuleNotFoundError("missing entities")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _import_module)

    with pytest.raises(PipelineError):
        run_nlp_to_db("dummy", normalized_dir, str(db_path), repo_root_dir=tmp_path)


def test_run_nlp_to_db_entities_failure_strict_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir(parents=True)
    db_path = tmp_path / "semantic" / "tags.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("semantic.nlp_runner.run_doc_terms_pipeline", lambda *_a, **_k: {"doc_terms": 0})

    fake_entities = types.ModuleType("semantic.entities_runner")

    def _boom(*_a, **_k):
        raise RuntimeError("entities failed")

    fake_entities.run_doc_entities_pipeline = _boom
    monkeypatch.setitem(sys.modules, "semantic.entities_runner", fake_entities)

    with pytest.raises(PipelineError):
        run_nlp_to_db("dummy", normalized_dir, str(db_path), repo_root_dir=tmp_path)


def test_run_nlp_to_db_persists_terms_and_folder_terms(tmp_path, monkeypatch):
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir()
    md_path = normalized_dir / "dummy.md"
    md_path.write_text("alpha beta", encoding="utf-8")

    db_path = tmp_path / "semantic" / "tags.db"
    ensure_schema_v2(str(db_path))

    with get_conn(str(db_path)) as conn:
        folder_id = upsert_folder(conn, "normalized", None)
        upsert_document(conn, folder_id, md_path.name, sha256="feedface", pages=2)

    monkeypatch.setattr("nlp.nlp_keywords.spacy_candidates", lambda text, lang: ["alpha", "beta"])
    monkeypatch.setattr("nlp.nlp_keywords.yake_scores", lambda text, top_k, lang: [("alpha", 0.9), ("beta", 0.4)])
    monkeypatch.setattr(
        "nlp.nlp_keywords.keybert_scores",
        lambda text, candidates, model_name, top_k: [("alpha", 0.8), ("beta", 0.3)],
    )
    monkeypatch.setattr(
        "nlp.nlp_keywords.fuse_and_dedup",
        lambda text, cand_spa, sc_y, sc_kb: [("alpha", 0.7), ("beta", 0.6)],
    )
    monkeypatch.setattr("nlp.nlp_keywords.topn_by_folder", lambda items, k: items[:k])

    def fake_cluster_synonyms(items, model_name, sim_thr):
        if not items:
            return []
        canonical, _ = max(items, key=lambda entry: entry[1])
        members = [phrase for phrase, _ in items]
        synonyms = [phrase for phrase in members if phrase != canonical]
        return [
            {
                "canonical": canonical,
                "members": members,
                "synonyms": synonyms,
            }
        ]

    monkeypatch.setattr("nlp.nlp_keywords.cluster_synonyms", fake_cluster_synonyms)

    # unit test isolation: bypass the entities pipeline for deterministic storage checks.
    stats = run_nlp_to_db("dummy", normalized_dir, str(db_path), enable_entities=False)

    with get_conn(str(db_path)) as conn:
        term_rows = conn.execute("SELECT canonical FROM terms").fetchall()
        alias_rows = conn.execute("SELECT alias FROM term_aliases").fetchall()
        folder_term_rows = conn.execute("SELECT term_id, weight FROM folder_terms").fetchall()

    assert stats["terms"] >= 1
    assert term_rows
    assert alias_rows
    assert folder_term_rows


def test_run_nlp_to_db_rejects_paths_outside_base(tmp_path):
    base_dir = tmp_path / "client"
    normalized_dir = base_dir / "normalized"
    normalized_dir.mkdir(parents=True)
    db_outside = tmp_path.parent / "outside" / "tags.db"

    with pytest.raises(PathTraversalError):
        run_nlp_to_db("dummy", normalized_dir, db_outside, repo_root_dir=base_dir)


def test_scan_normalized_requires_repo_root_dir_in_strict(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir(parents=True)
    db_path = tmp_path / "semantic" / "tags.db"

    with pytest.raises(ConfigError):
        scan_normalized_to_db(normalized_dir, db_path)


def test_resolve_cli_paths_uses_context_and_enforces_perimeter(tmp_path):
    base_dir = tmp_path / "client-sandbox"
    normalized_dir = base_dir / "normalized"
    semantic_dir = base_dir / "semantic"
    normalized_dir.mkdir(parents=True)
    semantic_dir.mkdir(parents=True)
    (base_dir / "raw").mkdir(parents=True)
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True)
    (book_dir / "README.md").write_text("# book", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("# summary", encoding="utf-8")
    (base_dir / "logs").mkdir(parents=True)
    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    ctx = TestClientCtx(
        slug="dummy",
        repo_root_dir=base_dir,
        semantic_dir=semantic_dir,
        config_dir=base_dir / "config",
        redact_logs=False,
        run_id=None,
    )

    resolved_base, resolved_normalized, db_path, resolved_semantic = _resolve_cli_paths(
        ctx,
        normalized_override=None,
        db_override=None,
    )

    assert resolved_base == base_dir.resolve()
    assert resolved_normalized == normalized_dir.resolve()
    assert resolved_semantic == semantic_dir.resolve()
    assert db_path == (semantic_dir / "tags.db").resolve()

    outside_normalized = tmp_path / "elsewhere" / "normalized"
    with pytest.raises(PathTraversalError):
        _resolve_cli_paths(ctx, normalized_override=str(outside_normalized), db_override=None)

    inside_db = semantic_dir / "custom.db"
    _, _, custom_db_path, _ = _resolve_cli_paths(
        ctx,
        normalized_override=None,
        db_override=str(inside_db),
    )
    assert custom_db_path == inside_db.resolve()
