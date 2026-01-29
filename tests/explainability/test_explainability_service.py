# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging

import pytest

from explainability.manifest import ResponseManifest
from explainability.service import ExplainabilityService
from pipeline.file_utils import safe_write_text
from storage.kb_db import insert_chunks


def _base_manifest() -> ResponseManifest:
    return {
        "response_id": "resp-123",
        "timestamp": "2025-01-01T00:00:00Z",
        "slug": "acme",
        "scope": "kb",
        "query": "ciao",
        "retriever_params": {"k": 2, "candidate_limit": 800},
        "model": {"embedding_model": "embed-model"},
        "evidence": [
            {"rank": 1, "score": 0.9, "source_id": "s1", "chunk_id": "c1", "path": "book/foo.md"},
            {"rank": 2, "score": 0.5, "source_id": "s2", "chunk_id": "c2", "path": "book/bar.md"},
        ],
        "metrics": {"candidates_loaded": 2, "evaluated": 2},
        "lineage_refs": [
            {"source_id": "s1", "chunk_id": "c1"},
            {"source_id": "s2", "chunk_id": "c2"},
        ],
        "flags": {"budget_hit": False},
    }


def test_build_response_packet_basic() -> None:
    svc = ExplainabilityService()
    manifest = _base_manifest()

    packet = svc.build_response_packet("acme", "resp-123", manifest, detail="standard")

    assert packet["response"]["response_id"] == "resp-123"
    assert packet["question"]["slug"] == "acme"
    assert packet["question"]["params"]["candidate_limit"] == 800
    assert packet["retrieval"]["model"]["embedding_model"] == "embed-model"
    assert len(packet["evidence"]) == 2
    assert packet["evidence"][0]["rank"] == 1
    assert packet["evidence"][0]["source_id"] == "s1"
    assert len(packet["lineage"]) == 2
    assert packet["lineage"][1]["chunk_id"] == "c2"
    assert packet["logs_ref"] == {"semantic": [], "retriever": []}


def test_build_response_packet_no_lineage() -> None:
    svc = ExplainabilityService()
    manifest = _base_manifest()
    manifest["evidence"] = [{"rank": 1, "score": 0.1}]

    packet = svc.build_response_packet("acme", "resp-123", manifest, detail="standard")

    assert packet["evidence"][0]["source_id"] is None
    assert packet["lineage"][0]["source_id"] is None
    assert packet["lineage"][0]["chunk_id"] is None


def test_build_response_packet_detail_modes() -> None:
    svc = ExplainabilityService()
    manifest = _base_manifest()

    packet_standard = svc.build_response_packet("acme", "resp-123", manifest, detail="standard")
    packet_full = svc.build_response_packet("acme", "resp-123", manifest, detail="full")

    assert packet_standard["retrieval"]["detail"] == "standard"
    assert packet_full["retrieval"]["detail"] == "full"
    # Per ora i contenuti sono identici a parte il flag detail
    packet_standard_cmp = dict(packet_standard)
    packet_full_cmp = dict(packet_full)
    packet_standard_cmp["retrieval"] = dict(packet_standard["retrieval"])
    packet_full_cmp["retrieval"] = dict(packet_full["retrieval"])
    packet_standard_cmp["retrieval"].pop("detail", None)
    packet_full_cmp["retrieval"].pop("detail", None)
    assert packet_standard_cmp == packet_full_cmp


def test_response_packet_lineage_enriched(tmp_path) -> None:
    svc = ExplainabilityService()
    db_path = tmp_path / "kb.sqlite"
    chunks = ["foo content"]
    embeddings = [[0.1, 0.2, 0.3]]
    meta = {
        "lineage": {
            "source_id": "s1",
            "version": "v1",
            "chunks": [{"chunk_id": "c1", "chunk_index": 0, "path": "book/foo.md"}],
        },
        "path": "book/foo.md",
    }
    insert_chunks("acme", "kb", "book/foo.md", "v1", meta, chunks, embeddings, db_path=db_path)
    manifest = _base_manifest()
    manifest["evidence"] = [{"rank": 1, "score": 0.9, "source_id": "s1", "chunk_id": "c1"}]
    manifest["scope"] = "kb"

    packet = svc.build_response_packet("acme", "resp-123", manifest, db_path=str(db_path))

    assert packet["lineage"][0]["status"] == "resolved"
    assert packet["lineage"][0]["path"] == "book/foo.md"
    assert packet["lineage"][0]["version"] == "v1"
    assert packet["lineage"][0]["chunk_index"] == 0


def test_response_packet_logs_ref_populated(caplog: pytest.LogCaptureFixture) -> None:
    svc = ExplainabilityService()
    manifest = _base_manifest()
    manifest["evidence"] = [{"rank": 1, "score": 0.9, "source_id": "s1", "chunk_id": "c1"}]
    logger = logging.getLogger("timmy_kb.retriever")

    with caplog.at_level(logging.INFO):
        logger.info(
            "retriever.evidence.selected", extra={"response_id": "resp-123", "source_id": "s1", "chunk_id": "c1"}
        )

    packet = svc.build_response_packet("acme", "resp-123", manifest, log_records=caplog.records)

    assert packet["logs_ref"]["retriever"]
    event = packet["logs_ref"]["retriever"][0]
    assert event["event"] == "retriever.evidence.selected"


def test_response_packet_unresolved_entries(tmp_path) -> None:
    svc = ExplainabilityService()
    db_path = tmp_path / "kb.sqlite"
    manifest = _base_manifest()
    manifest["evidence"] = [{"rank": 1, "score": 0.9, "source_id": "missing", "chunk_id": "missing"}]
    manifest["scope"] = "kb"
    safe_write_text(tmp_path / "dummy.txt", "x")  # ensure path utils ok

    packet = svc.build_response_packet("acme", "resp-123", manifest, db_path=str(db_path))

    assert packet["lineage"][0]["status"] == "unresolved"
