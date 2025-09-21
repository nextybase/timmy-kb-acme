from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, List


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

    monkeypatch.setitem(sys.modules, "pipeline.context", SimpleNamespace(ClientContext=_Ctx))

    # Stub logger
    class _Log:
        def info(self, *_a, **_k): ...
        def warning(self, *_a, **_k): ...

    monkeypatch.setitem(sys.modules, "pipeline.logging_utils", SimpleNamespace(get_structured_logger=lambda *_: _Log()))

    # Stub retriever: restituisce finti documenti con attributo path
    class _Doc:
        def __init__(self, p: Path):
            self.path = p

    def _retrieve(base_dir: Path, text: str, params: Any) -> Iterable[_Doc]:  # noqa: ARG001
        return [_Doc(base_dir / "book" / "a.md"), _Doc(base_dir / "book" / "b.md")]

    class _QP:
        def __init__(self, candidate_limit: int, latency_budget_ms: Any, auto_by_budget: bool):  # noqa: ARG002
            self.candidate_limit = candidate_limit

    monkeypatch.setitem(sys.modules, "retriever", SimpleNamespace(retrieve=_retrieve, QueryParams=_QP))

    # Forza root di ensure_within_and_resolve e safe_write_text
    writes: List[Path] = []

    def _ensure(root: Path, child: Path) -> Path:
        # Deve rispettare il root simulato (dir corrente)
        assert str(child).startswith(str(Path(".").resolve()))
        return child

    def _safe_write_text(p: Path, data: str, *, encoding: str, atomic: bool) -> None:  # noqa: ARG001
        assert atomic is True
        writes.append(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")

    monkeypatch.setitem(sys.modules, "pipeline.path_utils", SimpleNamespace(ensure_within_and_resolve=_ensure))
    monkeypatch.setitem(sys.modules, "pipeline.file_utils", SimpleNamespace(safe_write_text=_safe_write_text))

    # Import modulo e invoca main() con argv simulati
    mod = importlib.import_module("src.tools.retriever_calibrate")
    sys.argv = [
        "retriever_calibrate.py",
        "--slug",
        "x",
        "--queries",
        str(qfile),
        "--repetitions",
        "1",
        "--limits",
        "2",
        "--dump-top",
        str(tmp_path / "out" / "dump.jsonl"),
    ]
    code = mod.main()
    assert code == 0

    # Il dump deve esistere e contenere 1 riga
    dump_path = tmp_path / "out" / "dump.jsonl"
    assert dump_path.exists()
    content = dump_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1
    rec = json.loads(content[0])
    assert rec["limit"] == 2
    assert rec["docs"]  # lista non vuota

    # Verifica scrittura unica e atomica (una sola chiamata registrata)
    assert writes and writes[0] == dump_path
