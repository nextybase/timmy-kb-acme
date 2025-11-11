# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.logging_utils import get_structured_logger
from semantic.api import write_summary_and_readme


def _make_context(tmp_path: Path, slug: str):
    base_dir = tmp_path / f"timmy-kb-{slug}"
    book_dir = base_dir / "book"
    semantic_dir = base_dir / "semantic"
    raw_dir = base_dir / "raw"
    for folder in (
        base_dir,
        book_dir,
        semantic_dir,
        raw_dir,
        base_dir / "logs",
        base_dir / "config",
    ):
        folder.mkdir(parents=True, exist_ok=True)

    (base_dir / "config" / "config.yaml").write_text(
        """
client_name: Dummy
openai:
  timeout: 60
  max_retries: 2
  http2_enabled: false
vision:
  engine: assistants
  model: gpt-4o-mini-2024-07-18
  assistant_id_env: TEST_ASSISTANT_ID
  snapshot_retention_days: 30
retriever:
  auto_by_budget: false
  throttle:
    candidate_limit: 4000
    latency_budget_ms: 0
    parallelism: 1
    sleep_ms_between_calls: 0
ui:
  skip_preflight: true
  allow_local_only: true
  admin_local_mode: false
ops:
  log_level: INFO
finance:
  import_enabled: false
""",
        encoding="utf-8",
    )

    from pipeline.context import ClientContext

    return ClientContext.load(slug=slug, require_env=False)


def test_book_artifacts_are_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy"
    base_dir = tmp_path / f"timmy-kb-{slug}"
    monkeypatch.setenv("REPO_ROOT_DIR", str(base_dir))

    context = _make_context(tmp_path, slug)
    logger = get_structured_logger("contract-artifacts-test")

    write_summary_and_readme(context, logger, slug=slug)

    readme = base_dir / "book" / "README.md"
    summary = base_dir / "book" / "SUMMARY.md"

    assert readme.exists(), "README.md not generated"
    assert summary.exists(), "SUMMARY.md not generated"
    assert readme.read_text(encoding="utf-8").strip(), "README.md is empty"
    assert summary.read_text(encoding="utf-8").strip(), "SUMMARY.md is empty"
