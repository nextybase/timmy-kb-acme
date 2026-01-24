# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

import semantic.api as sapi
from pipeline.exceptions import ConfigError, exit_code_for
from tests.support.contexts import TestClientCtx
from timmy_kb.cli import semantic_onboarding as cli


def _ctx(base_dir: Path) -> TestClientCtx:
    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text("client_name: dummy\n", encoding="utf-8")
    return TestClientCtx(
        slug="dummy",
        repo_root_dir=base_dir,
        semantic_dir=base_dir / "semantic",
        config_dir=config_dir,
    )


def test_main_uses_vocab_before_enrichment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = argparse.Namespace(slug="dummy", no_preview=False, non_interactive=False)
    monkeypatch.setattr(cli, "_parse_args", lambda: args)
    monkeypatch.setattr(cli, "_require_normalize_raw_gate", lambda *_a, **_k: None)

    ctx = _ctx(tmp_path / "output" / "dummy")
    monkeypatch.setattr(cli.ClientContext, "load", classmethod(lambda cls, slug, **_: ctx))

    calls: list[object] = []
    monkeypatch.setattr(cli, "convert_markdown", lambda *_, **__: calls.append("convert"))
    monkeypatch.setattr(sapi, "convert_markdown", lambda *_, **__: calls.append("convert"))
    vocab = {"areas": {"area": ["term"]}}

    def _require(base_dir: Path, logger: object, *, slug: str) -> dict[str, dict[str, list[str]]]:
        calls.append(("require", slug))
        return vocab

    def _enrich(ctx_obj: object, logger: object, vocab_obj: object, *, slug: str) -> list[Path]:
        calls.append(("enrich", vocab_obj))
        return [ctx.repo_root_dir / "book" / "doc.md"]

    monkeypatch.setattr(cli, "require_reviewed_vocab", _require)
    monkeypatch.setattr(cli, "enrich_frontmatter", _enrich)
    monkeypatch.setattr(cli, "write_summary_and_readme", lambda *_, **__: calls.append("write"))
    # Allinea anche il modulo semantic.api usato da run_semantic_pipeline
    monkeypatch.setattr(sapi, "require_reviewed_vocab", _require)
    monkeypatch.setattr(sapi, "_require_reviewed_vocab", _require)
    monkeypatch.setattr(sapi, "enrich_frontmatter", _enrich)
    monkeypatch.setattr(sapi, "write_summary_and_readme", lambda *_, **__: calls.append("write"))

    exit_code = cli.main()

    assert exit_code == 0
    assert calls[:3] == ["convert", ("require", "dummy"), ("enrich", vocab)]


def test_main_bubbles_config_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = argparse.Namespace(slug="dummy", no_preview=False, non_interactive=True)
    monkeypatch.setattr(cli, "_parse_args", lambda: args)
    monkeypatch.setattr(cli, "_require_normalize_raw_gate", lambda *_a, **_k: None)

    ctx = _ctx(tmp_path / "output" / "dummy")
    monkeypatch.setattr(cli.ClientContext, "load", classmethod(lambda cls, slug, **_: ctx))

    monkeypatch.setattr(cli, "convert_markdown", lambda *_, **__: None)
    monkeypatch.setattr(cli, "enrich_frontmatter", lambda *_, **__: [])
    monkeypatch.setattr(cli, "write_summary_and_readme", lambda *_, **__: None)
    monkeypatch.setattr(sapi, "convert_markdown", lambda *_, **__: None)
    monkeypatch.setattr(sapi, "enrich_frontmatter", lambda *_, **__: [])
    monkeypatch.setattr(sapi, "write_summary_and_readme", lambda *_, **__: None)

    def _raise(*_: object, **__: object) -> dict[str, dict[str, list[str]]]:
        raise ConfigError("missing", slug="dummy")

    monkeypatch.setattr(cli, "require_reviewed_vocab", _raise)
    monkeypatch.setattr(sapi, "require_reviewed_vocab", _raise)
    monkeypatch.setattr(sapi, "_require_reviewed_vocab", _raise)

    exit_code = cli.main()

    assert exit_code == exit_code_for(ConfigError("missing", slug="dummy"))


def test_tags_raw_path_is_resolved_within_semantic_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = argparse.Namespace(slug="dummy", no_preview=False, non_interactive=True)
    monkeypatch.setattr(cli, "_parse_args", lambda: args)
    monkeypatch.setattr(cli, "_require_normalize_raw_gate", lambda *_a, **_k: None)

    ctx = _ctx(tmp_path / "output" / "dummy")
    monkeypatch.setattr(cli.ClientContext, "load", classmethod(lambda cls, slug, **_: ctx))
    monkeypatch.setattr(cli, "run_semantic_pipeline", lambda *a, **k: (ctx.repo_root_dir, [], []))

    layout = SimpleNamespace(
        semantic_dir=ctx.semantic_dir,
        book_dir=ctx.repo_root_dir / "book",
        base_dir=ctx.repo_root_dir,
        repo_root_dir=ctx.repo_root_dir,
        config_path=ctx.config_dir / "config.yaml",
        slug=ctx.slug,
    )
    monkeypatch.setattr(cli.WorkspaceLayout, "from_context", classmethod(lambda cls, c: layout))

    layout.semantic_dir.mkdir(parents=True, exist_ok=True)
    (layout.semantic_dir / "tags_raw.json").write_text("{}", encoding="utf-8")

    called: list[Path] = []

    def _ensure(base_dir: Path, candidate: Path) -> Path:
        called.append(candidate)
        return candidate

    monkeypatch.setattr(cli, "ensure_within_and_resolve", _ensure)
    monkeypatch.setattr(cli, "build_kg_for_workspace", lambda *a, **k: None)

    exit_code = cli.main()

    assert exit_code == 0
    assert called
    assert layout.semantic_dir / "tags_raw.json" in called
