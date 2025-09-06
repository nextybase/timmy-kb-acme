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

    calls = {"summary": 0, "readme": 0, "validate": 0, "fallback": 0}

    def _summary_stub(ctx):
        calls["summary"] += 1

    def _readme_stub(ctx):
        calls["readme"] += 1

    def _validate_stub(ctx):
        calls["validate"] += 1

    def _fallback_stub(context, logger):
        calls["fallback"] += 1

    # Patch optional generators and validator to our stubs
    monkeypatch.setattr(sapi, "_gen_summary", _summary_stub, raising=False)
    monkeypatch.setattr(sapi, "_gen_readme", _readme_stub, raising=False)
    monkeypatch.setattr(sapi, "_validate_md", _validate_stub, raising=False)
    monkeypatch.setattr(sapi, "ensure_readme_summary", _fallback_stub, raising=True)

    sapi.write_summary_and_readme(DummyCtx(), logging.getLogger("test"), slug="x")

    assert calls == {"summary": 1, "readme": 1, "validate": 1, "fallback": 1}


def test_write_summary_and_readme_generators_fail_but_fallback_runs(
    monkeypatch, tmp_path: Path
) -> None:
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

    calls = {"summary": 0, "readme": 0, "validate": 0, "fallback": 0}

    def _summary_stub(ctx):
        calls["summary"] += 1
        raise RuntimeError("boom summary")

    def _readme_stub(ctx):
        calls["readme"] += 1
        raise RuntimeError("boom readme")

    def _validate_stub(ctx):
        calls["validate"] += 1

    def _fallback_stub(context, logger):
        calls["fallback"] += 1

    monkeypatch.setattr(sapi, "_gen_summary", _summary_stub, raising=False)
    monkeypatch.setattr(sapi, "_gen_readme", _readme_stub, raising=False)
    monkeypatch.setattr(sapi, "_validate_md", _validate_stub, raising=False)
    monkeypatch.setattr(sapi, "ensure_readme_summary", _fallback_stub, raising=True)

    sapi.write_summary_and_readme(DummyCtx(), logging.getLogger("test"), slug="x")

    # Generators attempted and failed; fallback still invoked; validate still called
    assert calls["summary"] == 1 and calls["readme"] == 1
    assert calls["fallback"] == 1
    assert calls["validate"] == 1
