# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import semantic.api as sapi
from pipeline.exceptions import ConfigError, exit_code_for
from pipeline.qa_evidence import QA_EVIDENCE_FILENAME
from storage import decision_ledger
from tests.support.contexts import TestClientCtx
from timmy_kb.cli import semantic_onboarding as cli


def _ctx(base_dir: Path) -> TestClientCtx:
    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text("client_name: dummy\n", encoding="utf-8")
    for child in ("raw", "normalized", "book", "semantic", "logs"):
        (base_dir / child).mkdir(parents=True, exist_ok=True)
    (base_dir / "semantic" / "semantic_mapping.yaml").write_text("version: 1\nareas: {}\n", encoding="utf-8")
    book_dir = base_dir / "book"
    (book_dir / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    ctx = TestClientCtx(
        slug="dummy",
        repo_root_dir=base_dir,
        semantic_dir=base_dir / "semantic",
        config_dir=config_dir,
    )
    setattr(ctx, "config_path", config_dir / "config.yaml")
    return ctx


@pytest.fixture(autouse=True)
def ensure_strict_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")


def test_main_uses_vocab_before_enrichment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = argparse.Namespace(slug="dummy", no_preview=False, non_interactive=False)
    monkeypatch.setattr(cli, "_parse_args", lambda: args)
    monkeypatch.setattr(cli, "_require_normalize_raw_gate", lambda *_a, **_k: None)

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")

    ctx = _ctx(tmp_path / "output" / "dummy")
    load_kwargs: dict[str, object] = {}

    def _load_stub(cls: type[object], slug: str, **kwargs: object) -> TestClientCtx:
        load_kwargs.update(kwargs)
        return ctx

    monkeypatch.setattr(cli.ClientContext, "load", classmethod(_load_stub))
    book_dir = ctx.repo_root_dir / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (book_dir / "doc.md").write_text("content", encoding="utf-8")
    (ctx.config_dir / "ledger.db").write_text("", encoding="utf-8")
    logs_dir = ctx.repo_root_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    qa_payload = {
        "schema_version": 1,
        "qa_status": "pass",
        "checks_executed": ["pre-commit run --all-files", "pytest -q"],
    }
    (logs_dir / QA_EVIDENCE_FILENAME).write_text(json.dumps(qa_payload) + "\n", encoding="utf-8")

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
    assert load_kwargs.get("bootstrap_config") is False


def test_main_bubbles_config_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = argparse.Namespace(slug="dummy", no_preview=False, non_interactive=True)
    monkeypatch.setattr(cli, "_parse_args", lambda: args)
    monkeypatch.setattr(cli, "_require_normalize_raw_gate", lambda *_a, **_k: None)

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")

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

    logs_dir = ctx.repo_root_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    qa_payload = {
        "schema_version": 1,
        "qa_status": "pass",
        "checks_executed": ["pre-commit run --all-files", "pytest -q"],
    }
    (logs_dir / QA_EVIDENCE_FILENAME).write_text(json.dumps(qa_payload) + "\n", encoding="utf-8")

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
        logs_dir=ctx.repo_root_dir / "logs",
        slug=ctx.slug,
    )
    monkeypatch.setattr(cli.WorkspaceLayout, "from_context", classmethod(lambda cls, c: layout))

    layout.semantic_dir.mkdir(parents=True, exist_ok=True)
    layout.book_dir.mkdir(parents=True, exist_ok=True)
    (layout.book_dir / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (layout.book_dir / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (layout.book_dir / "doc.md").write_text("content", encoding="utf-8")
    (ctx.config_dir / "ledger.db").write_text("", encoding="utf-8")
    (layout.semantic_dir / "tags_raw.json").write_text("{}", encoding="utf-8")
    (layout.semantic_dir / "kg.tags.json").write_text("{}", encoding="utf-8")
    (layout.semantic_dir / "kg.tags.md").write_text("dummy", encoding="utf-8")
    layout.logs_dir.mkdir(parents=True, exist_ok=True)
    qa_payload = {
        "schema_version": 1,
        "qa_status": "pass",
        "checks_executed": ["pre-commit run --all-files", "pytest -q"],
    }
    (layout.logs_dir / QA_EVIDENCE_FILENAME).write_text(json.dumps(qa_payload) + "\n", encoding="utf-8")

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


def test_failure_record_contract_unexpected_error(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path / "output" / "dummy")
    layout = cli.WorkspaceLayout.from_context(ctx)
    requested = {"preview": "enabled", "interactive": "enabled", "tag_kg": "auto"}
    effective = dict(requested)

    record = cli.build_normative_failure_record(
        exc=RuntimeError("boom"),
        code=99,
        layout=layout,
        requested=requested,
        effective=effective,
        slug="dummy",
        run_id="run-1",
        decision_id="decision-1",
        decided_at="2026-01-01T00:00:00Z",
    )

    assert record.reason_code == "deny_unexpected_error"
    assert record.stop_code == decision_ledger.STOP_CODE_UNEXPECTED_ERROR
