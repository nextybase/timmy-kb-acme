# SPDX-License-Identifier: GPL-3.0-only
# tests/test_retriever_calibrate_io.py
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def test_dump_is_written_atomically_and_within_root(tmp_path, monkeypatch):
    qfile = tmp_path / "queries.jsonl"
    qfile.write_text(json.dumps({"text": "hello", "k": 2}) + "\n", encoding="utf-8")

    class _Ctx:
        def __init__(self, slug: str, base: Path) -> None:
            self.slug = slug
            self.repo_root_dir = base
            self.base_dir = base

        @classmethod
        def load(cls, *, slug: str, **_kwargs: Any) -> "_Ctx":
            base = tmp_path / "output" / f"timmy-kb-{slug}"
            return cls(slug, base)

    log_info_calls: list[tuple[str, dict[str, Any] | None]] = []
    log_warning_calls: list[tuple[str, dict[str, Any] | None]] = []

    class _Log:
        def info(self, event: str, *, extra: dict[str, Any] | None = None) -> None:
            log_info_calls.append((event, extra))

        def warning(self, event: str, *, extra: dict[str, Any] | None = None) -> None:
            log_warning_calls.append((event, extra))

    monkeypatch.setitem(sys.modules, "pipeline.context", SimpleNamespace(ClientContext=_Ctx))
    monkeypatch.setitem(
        sys.modules,
        "pipeline.logging_utils",
        SimpleNamespace(get_structured_logger=lambda *_: _Log()),
    )

    created_params: list[dict[str, Any]] = []
    retrieve_calls: list[Any] = []

    class _QueryParams:
        def __init__(
            self,
            *,
            db_path: Path | None,
            slug: str,
            scope: str,
            query: str,
            k: int,
            candidate_limit: int,
        ) -> None:
            created_params.append(
                {
                    "db_path": db_path,
                    "slug": slug,
                    "scope": scope,
                    "query": query,
                    "k": k,
                    "candidate_limit": candidate_limit,
                }
            )
            self.db_path = db_path
            self.slug = slug
            self.scope = scope
            self.query = query
            self.k = k
            self.candidate_limit = candidate_limit

    def _retrieve_candidates(params: _QueryParams) -> list[dict[str, Any]]:
        retrieve_calls.append(params)
        return [
            {"meta": {"path": "book/a.md"}},
            {"meta": {"id": "chunk-1"}},
        ]

    monkeypatch.setitem(
        sys.modules,
        "timmy_kb.cli.retriever",
        SimpleNamespace(
            QueryParams=_QueryParams,
            RetrieverError=RuntimeError,
            retrieve_candidates=_retrieve_candidates,
        ),
    )

    def _read_text_safe(base: Path, candidate: Path, *, encoding: str = "utf-8") -> str:
        base_resolved = Path(base).resolve()
        candidate_resolved = Path(candidate).resolve()
        candidate_resolved.relative_to(base_resolved)
        return candidate_resolved.read_text(encoding=encoding)

    def _ensure_within_and_resolve(base: Path, candidate: Path) -> Path:
        base_resolved = Path(base).resolve()
        candidate_resolved = Path(candidate).resolve()
        candidate_resolved.relative_to(base_resolved)
        return candidate_resolved

    writes: list[Path] = []

    def _safe_write_text(path: Path, data: str, *, encoding: str, atomic: bool) -> None:
        assert atomic is True
        resolved = Path(path).resolve()
        resolved.relative_to(Path(".").resolve())
        writes.append(resolved)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(data, encoding=encoding)

    monkeypatch.setitem(
        sys.modules,
        "pipeline.path_utils",
        SimpleNamespace(
            read_text_safe=_read_text_safe,
            ensure_within_and_resolve=_ensure_within_and_resolve,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "pipeline.file_utils",
        SimpleNamespace(safe_write_text=_safe_write_text),
    )

    sys.modules.pop("src.tools.retriever_calibrate", None)
    mod = importlib.import_module("src.tools.retriever_calibrate")

    dump_path = Path("tmp_calibrate_io") / "dump.jsonl"
    sys.argv = [
        "retriever_calibrate.py",
        "--slug",
        "dummy",
        "--scope",
        "faq",
        "--queries",
        str(qfile),
        "--repetitions",
        "1",
        "--limits",
        "2",
        "--dump-top",
        str(dump_path),
    ]

    code = mod.main()
    assert code == 0

    assert dump_path.exists()
    content = dump_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1
    record = json.loads(content[0])
    assert record["limit"] == 2
    assert record["docs"]

    assert writes and writes[0] == dump_path.resolve()

    assert created_params
    first_params = created_params[0]
    assert first_params == {
        "db_path": (tmp_path / "output" / "timmy-kb-dummy" / "semantic" / "kb.sqlite").resolve(),
        "slug": "dummy",
        "scope": "faq",
        "query": "hello",
        "k": 2,
        "candidate_limit": 2,
    }
    assert retrieve_calls

    assert any(event == "retriever_calibrate.run" for event, _extra in log_info_calls)
    assert any(event == "retriever_calibrate.start" for event, _extra in log_info_calls)
    assert not log_warning_calls
    dump_path.unlink(missing_ok=True)
    if dump_path.parent.exists():
        try:
            next(dump_path.parent.iterdir())
        except StopIteration:
            dump_path.parent.rmdir()
