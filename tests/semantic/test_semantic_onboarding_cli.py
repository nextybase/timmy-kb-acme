# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from tests.support.contexts import TestClientCtx

import semantic.api as sapi
import semantic_onboarding as cli
from pipeline.exceptions import ConfigError, exit_code_for


def _ctx(base_dir: Path) -> TestClientCtx:
    book_dir = base_dir / "book"
    return TestClientCtx(slug="dummy", base_dir=base_dir, raw_dir=base_dir / "raw", md_dir=book_dir)


def test_main_uses_vocab_before_enrichment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = argparse.Namespace(slug="dummy", no_preview=False, non_interactive=False)
    monkeypatch.setattr(cli, "_parse_args", lambda: args)

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
        return [ctx.base_dir / "book" / "doc.md"]

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
