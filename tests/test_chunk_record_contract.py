# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pipeline.types import ChunkRecord


def test_chunk_record_contract():
    """Verifica che ChunkRecord accetti la forma attesa."""

    record: ChunkRecord = {
        "id": "chunk-123",
        "slug": "dummy",
        "source_path": "clients/example/README.md",
        "text": "locale",
        "chunk_index": 0,
        "created_at": "2025-12-13T21:00:00Z",
        "metadata": {
            "tags": ["demo", "test"],
            "layout_section": "introduction",
        },
    }

    assert record["id"].startswith("chunk-")
    assert isinstance(record["chunk_index"], int)
    assert isinstance(record["metadata"], dict)
    assert isinstance(record["metadata"]["tags"], list)
    assert isinstance(record["metadata"]["layout_section"], str)
