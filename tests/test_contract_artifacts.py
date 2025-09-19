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

    (base_dir / "config" / "config.yaml").write_text("client_name: Dummy", encoding="utf-8")

    from pipeline.context import ClientContext

    return ClientContext.load(slug=slug, require_env=False)


def test_book_artifacts_are_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "contract-artifacts"
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
