# SPDX-License-Identifier: GPL-3.0-only

import pytest
from tests.support.contexts import TestClientCtx

from pipeline.exceptions import PathTraversalError
from storage.tags_store import ensure_schema_v2, get_conn
from storage.tags_store import save_doc_terms as real_save_doc_terms
from storage.tags_store import upsert_document, upsert_folder
from tag_onboarding import _resolve_cli_paths, run_nlp_to_db


def test_run_nlp_to_db_processes_nested_pdf(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    pdf_dir = raw_dir / "subdir"
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "dummy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% Codex test\n")

    db_path = tmp_path / "semantic" / "tags.db"
    ensure_schema_v2(str(db_path))

    with get_conn(str(db_path)) as conn:
        folder_id = upsert_folder(conn, "raw/subdir", "raw")
        doc_id = upsert_document(conn, folder_id, pdf_path.name, sha256="deadbeef", pages=1)

    captured_path: dict[str, str] = {}

    def fake_extract_text(path: str) -> str:
        captured_path["value"] = path
        return "dummy text"

    monkeypatch.setattr("nlp.nlp_keywords.extract_text_from_pdf", fake_extract_text)
    monkeypatch.setattr("nlp.nlp_keywords.spacy_candidates", lambda text, lang: ["alpha"])
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

    stats = run_nlp_to_db("dummy", raw_dir, str(db_path))

    assert captured_path["value"] == str(pdf_path)
    assert captured_doc_ids == [doc_id]
    assert captured_items
    assert stats["doc_terms"] == len(captured_items)


def test_run_nlp_to_db_persists_terms_and_folder_terms(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    pdf_path = raw_dir / "dummy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% Codex test\n")

    db_path = tmp_path / "semantic" / "tags.db"
    ensure_schema_v2(str(db_path))

    with get_conn(str(db_path)) as conn:
        folder_id = upsert_folder(conn, "raw", None)
        upsert_document(conn, folder_id, pdf_path.name, sha256="feedface", pages=2)

    monkeypatch.setattr("nlp.nlp_keywords.extract_text_from_pdf", lambda path: "alpha beta")
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

    stats = run_nlp_to_db("dummy", raw_dir, str(db_path))

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
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True)
    db_outside = tmp_path.parent / "outside" / "tags.db"

    with pytest.raises(PathTraversalError):
        run_nlp_to_db("dummy", raw_dir, db_outside, base_dir=base_dir)


def test_resolve_cli_paths_uses_context_and_enforces_perimeter(tmp_path):
    base_dir = tmp_path / "client-sandbox"
    raw_dir = base_dir / "custom-raw"
    semantic_dir = base_dir / "semantic-data"
    raw_dir.mkdir(parents=True)
    semantic_dir.mkdir(parents=True)
    ctx = TestClientCtx(
        slug="dummy",
        base_dir=base_dir,
        raw_dir=raw_dir,
        md_dir=base_dir / "book",
        repo_root_dir=None,
        semantic_dir=semantic_dir,
        redact_logs=False,
        run_id=None,
    )

    resolved_base, resolved_raw, db_path, resolved_semantic = _resolve_cli_paths(
        ctx,
        raw_override=None,
        db_override=None,
    )

    assert resolved_base == base_dir.resolve()
    assert resolved_raw == raw_dir.resolve()
    assert resolved_semantic == semantic_dir.resolve()
    assert db_path == (semantic_dir / "tags.db").resolve()

    outside_raw = tmp_path / "elsewhere" / "raw"
    with pytest.raises(PathTraversalError):
        _resolve_cli_paths(ctx, raw_override=str(outside_raw), db_override=None)

    inside_db = semantic_dir / "custom.db"
    _, _, custom_db_path, _ = _resolve_cli_paths(
        ctx,
        raw_override=None,
        db_override=str(inside_db),
    )
    assert custom_db_path == inside_db.resolve()
