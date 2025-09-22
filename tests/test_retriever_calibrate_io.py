# tests/test_retriever_calibrate_io.py
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


def test_dump_is_written_atomically_and_within_root(tmp_path, monkeypatch):
    # Prepara file queries JSONL
    qfile = tmp_path / "queries.jsonl"
    qfile.write_text(json.dumps({"text": "hello", "k": 2}) + "\n", encoding="utf-8")

    # Stub ClientContext
    class _Ctx:
        def __init__(self, base: Path):
            self.base_dir = base

        @classmethod
        def load(cls, **_k):
            return cls(tmp_path / "output" / "timmy-kb-x")

    monkeypatch.setitem(
        sys.modules,
        "pipeline.context",
        SimpleNamespace(ClientContext=_Ctx),
    )

    # Stub logger
    class _Log:
        def info(self, *_a, **_k): ...
        def warning(self, *_a, **_k): ...

    monkeypatch.setitem(
        sys.modules,
        "pipeline.logging_utils",
        SimpleNamespace(get_structured_logger=lambda *_: _Log()),
    )

    # Stub retriev
