# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_onboarding_exitcodes.py
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import semantic.api as sapi
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from timmy_kb.cli import semantic_onboarding as mod


class _DummyCtx(SimpleNamespace):
    base_dir: Path
    md_dir: Path
    slug: str


def _make_ctx(tmp_path: Path, slug: str = "dummy") -> _DummyCtx:
    base = tmp_path / "output" / f"timmy-kb-{slug}"
    book = base / "book"
    base.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    return _DummyCtx(base_dir=base, md_dir=book, slug=slug)


def _set_argv(slug: str = "dummy") -> None:
    sys.argv = ["semantic_onboarding.py", "--slug", slug, "--non-interactive"]


def test_cli_returns_configerror_exit_code(tmp_path: Path, monkeypatch: Any) -> None:
    _set_argv("dummy")

    # Evita I/O reale
    monkeypatch.setattr(
        mod,
        "ClientContext",
        SimpleNamespace(load=lambda **_: _make_ctx(tmp_path, "dummy")),
        raising=True,
    )

    # convert_markdown alza ConfigError
    def _raise_cfg(*_a: Any, **_k: Any) -> None:
        raise ConfigError("boom")

    monkeypatch.setattr(mod, "convert_markdown", _raise_cfg, raising=True)

    code = mod.main()
    assert code == exit_code_for(ConfigError("boom"))


def test_cli_returns_pipelineerror_exit_code(tmp_path: Path, monkeypatch: Any) -> None:
    _set_argv("dummy")

    monkeypatch.setattr(
        mod,
        "ClientContext",
        SimpleNamespace(load=lambda **_: _make_ctx(tmp_path, "dummy")),
        raising=True,
    )

    # convert ok
    monkeypatch.setattr(mod, "convert_markdown", lambda *_a, **_k: None, raising=True)
    monkeypatch.setattr(sapi, "convert_markdown", lambda *_a, **_k: None, raising=True)

    # get_paths compatto
    def _fake_get_paths(slug: str) -> dict[str, Path]:
        ctx = _make_ctx(tmp_path, slug)
        return {"base": ctx.base_dir, "book": ctx.md_dir}

    monkeypatch.setattr(mod, "get_paths", _fake_get_paths, raising=True)

    # vocab + enrich ok
    monkeypatch.setattr(mod, "require_reviewed_vocab", lambda _b, _l, **_k: {}, raising=True)
    monkeypatch.setattr(mod, "enrich_frontmatter", lambda *_a, **_k: ["A.md"], raising=True)
    monkeypatch.setattr(sapi, "_require_reviewed_vocab", lambda _b, _l, **_k: {}, raising=True)
    monkeypatch.setattr(sapi, "enrich_frontmatter", lambda *_a, **_k: ["A.md"], raising=True)

    # write_summary_and_readme alza PipelineError
    def _raise_pipe(*_a: Any, **_k: Any) -> None:
        raise PipelineError("ws boom")

    monkeypatch.setattr(mod, "write_summary_and_readme", _raise_pipe, raising=True)
    monkeypatch.setattr(sapi, "write_summary_and_readme", _raise_pipe, raising=True)

    code = mod.main()
    assert code == exit_code_for(PipelineError("ws boom"))


def test_cli_missing_vocab_db_returns_config_error(tmp_path: Path, monkeypatch: Any) -> None:
    _set_argv("dummy")

    ctx = _make_ctx(tmp_path, "dummy")
    monkeypatch.setattr(
        mod,
        "ClientContext",
        SimpleNamespace(load=lambda **_: ctx),
        raising=True,
    )

    monkeypatch.setattr(mod, "convert_markdown", lambda *_a, **_k: None, raising=True)

    def _fake_get_paths(slug: str) -> dict[str, Path]:
        return {"base": ctx.base_dir, "book": ctx.md_dir}

    monkeypatch.setattr(mod, "get_paths", _fake_get_paths, raising=True)

    def _raise_missing(*_a: Any, **_k: Any) -> None:
        raise ConfigError("vocabolario mancante")

    monkeypatch.setattr(mod, "require_reviewed_vocab", _raise_missing, raising=True)

    code = mod.main()
    assert code == exit_code_for(ConfigError("vocabolario mancante"))


def test_cli_summary_log_excludes_readme_summary(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica che il riepilogo strutturato riporti solo markdown di contenuto."""
    _set_argv("dummy")

    ctx = _make_ctx(tmp_path, "dummy")
    monkeypatch.setattr(
        mod,
        "ClientContext",
        SimpleNamespace(load=lambda **_: ctx),
        raising=True,
    )

    def _fake_convert(ctx_, logger, slug):
        (ctx_.md_dir / "README.md").write_text("# r\n", encoding="utf-8")
        (ctx_.md_dir / "SUMMARY.md").write_text("# s\n", encoding="utf-8")
        (ctx_.md_dir / "cat.md").write_text("# c\n", encoding="utf-8")
        return [ctx_.md_dir / "cat.md"]

    monkeypatch.setattr(mod, "convert_markdown", _fake_convert, raising=True)
    monkeypatch.setattr(sapi, "convert_markdown", _fake_convert, raising=True)

    def _fake_get_paths(slug: str) -> dict[str, Path]:
        return {"base": ctx.base_dir, "book": ctx.md_dir}

    monkeypatch.setattr(mod, "get_paths", _fake_get_paths, raising=True)
    monkeypatch.setattr(mod, "require_reviewed_vocab", lambda _b, _l, **_k: {}, raising=True)
    monkeypatch.setattr(mod, "enrich_frontmatter", lambda *_a, **_k: ["cat.md"], raising=True)
    monkeypatch.setattr(mod, "write_summary_and_readme", lambda *_a, **_k: None, raising=True)
    monkeypatch.setattr(sapi, "_require_reviewed_vocab", lambda _b, _l, **_k: {}, raising=True)
    monkeypatch.setattr(sapi, "enrich_frontmatter", lambda *_a, **_k: ["cat.md"], raising=True)
    monkeypatch.setattr(sapi, "write_summary_and_readme", lambda *_a, **_k: None, raising=True)

    captured: dict[str, object] = {}
    original_get_logger = mod.get_structured_logger

    class _TrackingLogger:
        def __init__(self, base_logger: Any):
            self._base = base_logger
            self.summary_extra: dict[str, object] | None = None

        def info(self, msg: str, *args, **kwargs):
            extra = kwargs.get("extra") or {}
            if msg == "cli.semantic_onboarding.summary":
                self.summary_extra = dict(extra)
            return self._base.info(msg, *args, **kwargs)

        def warning(self, msg: str, *args, **kwargs):
            return self._base.warning(msg, *args, **kwargs)

        def exception(self, msg: str, *args, **kwargs):
            return self._base.exception(msg, *args, **kwargs)

        def __getattr__(self, item: str):
            return getattr(self._base, item)

    def _capture_logger(*args, **kwargs):
        base_logger = original_get_logger(*args, **kwargs)
        tracker = _TrackingLogger(base_logger)
        captured["logger"] = tracker
        return tracker

    monkeypatch.setattr(mod, "get_structured_logger", _capture_logger, raising=True)

    code = mod.main()
    assert code == 0

    tracker = captured.get("logger")
    assert tracker is not None
    assert tracker.summary_extra is not None
    assert tracker.summary_extra.get("markdown") == 1
    assert tracker.summary_extra.get("summary_exists") is True
    assert tracker.summary_extra.get("readme_exists") is True
