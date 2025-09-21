# tests/test_semantic_onboarding_exitcodes.py
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pipeline.exceptions import ConfigError, PipelineError, exit_code_for


class _DummyCtx(SimpleNamespace):
    base_dir: Path
    md_dir: Path
    slug: str


def _make_ctx(tmp_path: Path, slug: str = "acme") -> _DummyCtx:
    base = tmp_path / "output" / f"timmy-kb-{slug}"
    book = base / "book"
    base.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    return _DummyCtx(base_dir=base, md_dir=book, slug=slug)


def _set_argv(slug: str = "acme") -> None:
    sys.argv = ["semantic_onboarding.py", "--slug", slug, "--non-interactive"]


def test_cli_returns_configerror_exit_code(tmp_path: Path, monkeypatch: Any) -> None:
    _set_argv("x")
    mod = importlib.import_module("src.semantic_onboarding")

    # Evita I/O reale
    monkeypatch.setattr(
        mod,
        "ClientContext",
        SimpleNamespace(load=lambda **_: _make_ctx(tmp_path, "x")),
        raising=True,
    )

    # convert_markdown alza ConfigError
    def _raise_cfg(*_a: Any, **_k: Any) -> None:
        raise ConfigError("boom")

    monkeypatch.setattr(mod, "convert_markdown", _raise_cfg, raising=True)

    code = mod.main()
    assert code == exit_code_for(ConfigError("boom"))


def test_cli_returns_pipelineerror_exit_code(tmp_path: Path, monkeypatch: Any) -> None:
    _set_argv("y")
    mod = importlib.import_module("src.semantic_onboarding")

    monkeypatch.setattr(
        mod,
        "ClientContext",
        SimpleNamespace(load=lambda **_: _make_ctx(tmp_path, "y")),
        raising=True,
    )

    # convert ok
    monkeypatch.setattr(mod, "convert_markdown", lambda *_a, **_k: None, raising=True)

    # get_paths compatto
    def _fake_get_paths(slug: str) -> dict[str, Path]:
        ctx = _make_ctx(tmp_path, slug)
        return {"base": ctx.base_dir, "book": ctx.md_dir}

    monkeypatch.setattr(mod, "get_paths", _fake_get_paths, raising=True)

    # vocab + enrich ok
    monkeypatch.setattr(mod, "load_reviewed_vocab", lambda _b, _l: {}, raising=True)
    monkeypatch.setattr(mod, "enrich_frontmatter", lambda *_a, **_k: ["A.md"], raising=True)

    # write_summary_and_readme alza PipelineError
    def _raise_pipe(*_a: Any, **_k: Any) -> None:
        raise PipelineError("ws boom")

    monkeypatch.setattr(mod, "write_summary_and_readme", _raise_pipe, raising=True)

    code = mod.main()
    assert code == exit_code_for(PipelineError("ws boom"))
