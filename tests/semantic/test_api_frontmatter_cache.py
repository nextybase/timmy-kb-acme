# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from pipeline.logging_utils import get_structured_logger

from semantic import api


def _prepare_workspace(base: Path, slug: str) -> Path:
    workspace = base / slug
    for directory in ("raw", "normalized", "book", "semantic", "logs"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    (workspace / "config" / "config.yaml").write_text("meta: client")
    (workspace / "book" / "README.md").write_text("# demo")
    (workspace / "book" / "SUMMARY.md").write_text("# summary")
    (workspace / "semantic" / "semantic_mapping.yaml").write_text("mapping: {}")
    return workspace


def test_clear_frontmatter_cache_failure_logs_service_event(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slug = "dummy-slug"
    workspace = _prepare_workspace(tmp_path, slug)
    context = SimpleNamespace(repo_root_dir=workspace, slug=slug, run_id="run-1234")
    logger = get_structured_logger("tests.semantic.api.cache")

    def _stub_convert(context_arg, logger_arg, *, slug: str):
        return [workspace / "raw" / "doc.md"]

    def _stub_vocab(repo_root_dir, logger_arg, *, slug: str):
        return {}

    def _stub_enrich(context_arg, logger_arg, vocab, *, slug: str):
        return [workspace / "semantic" / "enriched.md"]

    def _stub_summary(context_arg, logger_arg, *, slug: str):
        return None

    def _failing_clear(*args, **kwargs):
        raise RuntimeError("cache cleanup failed")

    monkeypatch.setattr(
        "pipeline.content_utils.clear_frontmatter_cache",
        _failing_clear,
    )
    monkeypatch.setattr(
        "pipeline.content_utils.log_frontmatter_cache_stats",
        lambda *args, **kwargs: None,
    )

    caplog.set_level(logging.WARNING)
    caplog.clear()

    result = api._run_build_workflow(
        context,
        logger,
        slug=slug,
        convert_fn=_stub_convert,
        vocab_fn=_stub_vocab,
        enrich_fn=_stub_enrich,
        summary_fn=_stub_summary,
    )

    assert result[0] == workspace
    service_records = [
        record
        for record in caplog.records
        if record.message == "semantic.frontmatter_cache.clear_failed"
    ]
    assert len(service_records) == 1
    record = service_records[0]
    assert record.slug == slug
    assert record.service == "semantic.frontmatter_cache"
    assert record.operation == "clear"
    assert record.service_only is True
    assert record.error_type == "RuntimeError"
    assert record.error == "cache cleanup failed"
