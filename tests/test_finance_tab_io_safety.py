# tests/test_finance_tab_io_safety.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import src.ui.tabs.finance as fin


class _DummyFile:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class _DummySt:
    def __init__(self, base: Path, data: bytes):
        self._msgs: Dict[str, Any] = {}
        self._file = _DummyFile(data)
        self._base = base
        self.session_state = {"run_id": "t"}

    # UI elements (no-op / record)
    def subheader(self, *_a, **_k): ...
    def caption(self, *_a, **_k): ...
    def info(self, *_a, **_k): ...
    def table(self, *_a, **_k): ...

    def columns(self, *_a, **_k):
        # Return a 2-tuple of context managers
        return (self, self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def file_uploader(self, *_a, **_k):
        return self._file

    def button(self, *_a, **_k) -> bool:
        # Simula click sul bottone
        return True

    def success(self, msg: str):
        self._msgs["success"] = msg

    def warning(self, msg: str):
        self._msgs["warning"] = msg

    def exception(self, exc: Exception):
        self._msgs["exception"] = str(exc)


class _DummyLogger:
    def info(self, *_a, **_k): ...
    def warning(self, *_a, **_k): ...
    def error(self, *_a, **_k): ...


def test_finance_tab_writes_inside_semantic_dir(tmp_path: Path, monkeypatch):
    """Verifica guardie ensure_within + scrittura atomica + cleanup finally."""
    base = tmp_path / "output" / "timmy-kb-acme"
    book = base / "book"
    (book).mkdir(parents=True, exist_ok=True)

    # Stub ClientContext.load per puntare a base
    class _Ctx:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir

        @classmethod
        def load(cls, **_k):
            return cls(base)

    monkeypatch.setattr("pipeline.context.ClientContext", _Ctx, raising=True)

    # Patch safe_write_bytes e ensure_within per osservare chiamate e validare path
    calls: Dict[str, Path] = {}

    def _safe_write_bytes(path: Path, data: bytes, *, atomic: bool) -> None:
        # deve scrivere sotto base/semantic
        calls["path"] = path
        assert atomic is True
        path.write_bytes(data)

    def _ensure_within(root: Path, child: Path) -> None:
        rp = child.resolve()
        assert str(rp).startswith(str(root.resolve()))

    monkeypatch.setattr("pipeline.file_utils.safe_write_bytes", _safe_write_bytes, raising=True)
    monkeypatch.setattr("pipeline.path_utils.ensure_within", _ensure_within, raising=True)

    # Patch fin_import_csv: registra che viene invocato e restituisce un risultato fittizio
    def _fin_import_csv(base_dir: Path, csv_path: Path) -> Dict[str, object]:
        assert base_dir == base
        assert csv_path.parent == base / "semantic"
        return {"rows": 3, "db": str(base / "semantic" / "finance.db")}

    def _fin_summarize(base_dir: Path):
        return [("m", 3)]

    monkeypatch.setattr("finance.api.import_csv", _fin_import_csv, raising=True)
    monkeypatch.setattr("finance.api.summarize_metrics", _fin_summarize, raising=True)

    ui = _DummySt(base, b"metric,period,value\nm,2023Q1,1\n")
    fin.render_finance_tab(st=ui, log=_DummyLogger(), slug="acme")

    # file temporaneo deve essere stato rimosso (cleanup finally)
    sem_dir = base / "semantic"
    assert sem_dir.exists()
    assert not any(p.name.startswith("tmp-finance-") for p in sem_dir.iterdir())

    # safe_write_bytes chiamato ed entro confini sem_dir
    tmp_written = calls.get("path")
    assert tmp_written is not None
    assert tmp_written.parent == sem_dir
