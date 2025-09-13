from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import semantic.api as sapi


@dataclass
class DummyCtx:
    slug: str = "x"


def test_write_summary_and_readme_happy_path(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True)

    # Constrain I/O under tmp path
    monkeypatch.setattr(
        sapi,
        "get_paths",
        lambda slug: {
            "base": base,
            "raw": base / "raw",
            "book": book,
            "semantic": base / "semantic",
        },
    )

    calls = {"summary": 0, "readme": 0, "validate": 0}

    def _summary_stub(ctx):
        calls["summary"] += 1

    def _readme_stub(ctx):
        calls["readme"] += 1

    def _validate_stub(ctx):
        calls["validate"] += 1

    # Patch optional generators and validator to our stubs
    monkeypatch.setattr(sapi, "_gen_summary", _summary_stub, raising=False)
    monkeypatch.setattr(sapi, "_gen_readme", _readme_stub, raising=False)
    monkeypatch.setattr(sapi, "_validate_md", _validate_stub, raising=False)

    sapi.write_summary_and_readme(DummyCtx(), logging.getLogger("test"), slug="x")

    assert calls == {"summary": 1, "readme": 1, "validate": 1}


def test_write_summary_and_readme_generators_fail_raise(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True)

    monkeypatch.setattr(
        sapi,
        "get_paths",
        lambda slug: {
            "base": base,
            "raw": base / "raw",
            "book": book,
            "semantic": base / "semantic",
        },
    )

    calls = {"summary": 0, "readme": 0, "validate": 0}

    def _summary_stub(ctx):
        calls["summary"] += 1
        raise RuntimeError("boom summary")

    def _readme_stub(ctx):
        calls["readme"] += 1
        raise RuntimeError("boom readme")

    def _validate_stub(ctx):
        calls["validate"] += 1

    monkeypatch.setattr(sapi, "_gen_summary", _summary_stub, raising=False)
    monkeypatch.setattr(sapi, "_gen_readme", _readme_stub, raising=False)
    monkeypatch.setattr(sapi, "_validate_md", _validate_stub, raising=False)

    import pytest

    with pytest.raises(RuntimeError):
        sapi.write_summary_and_readme(DummyCtx(), logging.getLogger("test"), slug="x")

    # Generators attempted e hanno sollevato
    assert calls["summary"] == 1 and calls["readme"] == 1
    # Nessun fallback; validazione non raggiunta
    assert calls["validate"] == 0
