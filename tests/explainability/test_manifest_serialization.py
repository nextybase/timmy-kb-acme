# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
from pathlib import Path

from explainability.manifest import ResponseManifest
from explainability.serialization import safe_write_manifest


def _manifest() -> ResponseManifest:
    return {
        "response_id": "resp-001",
        "timestamp": "2025-01-01T00:00:00Z",
        "slug": "acme",
        "scope": "kb",
        "query": "hi",
        "retriever_params": {"k": 1, "candidate_limit": 500},
        "model": {"embedding_model": "embed-model"},
        "evidence": [{"rank": 1, "score": 0.9, "source_id": "s1", "chunk_id": "c1"}],
        "metrics": {"candidates_loaded": 1, "evaluated": 1},
        "lineage_refs": [{"source_id": "s1", "chunk_id": "c1"}],
        "flags": {},
    }


def test_safe_write_manifest_pathsafe(tmp_path: Path) -> None:
    manifest = _manifest()
    out_path = safe_write_manifest(manifest, output_dir=tmp_path, response_id="resp-001")

    assert out_path.name == "resp-001.json"
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["response_id"] == "resp-001"
    assert data["retriever_params"]["k"] == 1


def test_safe_write_manifest_atomic(tmp_path: Path) -> None:
    manifest = _manifest()
    out_path = safe_write_manifest(manifest, output_dir=tmp_path, response_id="resp-atomic")
    temp_files = [p for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert out_path.exists()
    assert not temp_files  # safe_write_text rimuove il tmp


def test_manifest_saved_matches_input(tmp_path: Path) -> None:
    manifest = _manifest()
    out_path = safe_write_manifest(manifest, output_dir=tmp_path, response_id="resp-compare")
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    for key in ("response_id", "slug", "scope", "query", "retriever_params", "evidence"):
        assert loaded[key] == manifest[key]
