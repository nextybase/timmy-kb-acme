# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.content_utils import generate_readme_markdown, generate_summary_markdown
from pipeline.logging_utils import get_structured_logger
from pipeline.qa_evidence import QA_EVIDENCE_FILENAME
from semantic.frontmatter_service import write_summary_and_readme


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
        base_dir / "normalized",
        base_dir / "logs",
        base_dir / "config",
    ):
        folder.mkdir(parents=True, exist_ok=True)
    (book_dir / "README.md").write_text("# Placeholder\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("# Placeholder\n", encoding="utf-8")
    (semantic_dir / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (base_dir / "logs" / QA_EVIDENCE_FILENAME).write_text(
        '{"schema_version":1,"qa_status":"pass","checks_executed":["pytest -q"]}\n',
        encoding="utf-8",
    )

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
""",
        encoding="utf-8",
    )

    from pipeline.context import ClientContext

    return ClientContext.load(slug=slug, require_env=False)


def test_book_artifacts_are_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy"
    base_dir = tmp_path / f"timmy-kb-{slug}"
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(base_dir))

    def _summary_with_repo_root(paths):  # type: ignore[no-untyped-def]
        ctx = SimpleNamespace(repo_root_dir=paths.repo_root_dir, slug=paths.slug)
        return generate_summary_markdown(ctx, book_dir=paths.book_dir)

    def _readme_with_repo_root(paths):  # type: ignore[no-untyped-def]
        ctx = SimpleNamespace(repo_root_dir=paths.repo_root_dir, slug=paths.slug)
        return generate_readme_markdown(ctx, book_dir=paths.book_dir)

    monkeypatch.setattr("semantic.frontmatter_service._gen_summary", _summary_with_repo_root)
    monkeypatch.setattr("semantic.frontmatter_service._gen_readme", _readme_with_repo_root)

    context = _make_context(tmp_path, slug)
    logger = get_structured_logger("contract-artifacts-test")

    write_summary_and_readme(context, logger, slug=slug)

    readme = base_dir / "book" / "README.md"
    summary = base_dir / "book" / "SUMMARY.md"

    assert readme.exists(), "README.md not generated"
    assert summary.exists(), "SUMMARY.md not generated"
    assert readme.read_text(encoding="utf-8").strip(), "README.md is empty"
    assert summary.read_text(encoding="utf-8").strip(), "SUMMARY.md is empty"
