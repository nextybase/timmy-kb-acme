"""Tests per l'integrazione di ClientContext con Settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.settings import Settings
from tests.conftest import DUMMY_SLUG

pytestmark = pytest.mark.pipeline


@pytest.fixture()
def repo_with_config(tmp_path: Path) -> Path:
    repo_root = tmp_path / "workspace"
    config_dir = repo_root / "config"
    semantic_dir = repo_root / "semantic"
    config_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        """
vision:
  engine: assistant
  model: gpt-4o-mini-2024-07-18
  assistant_id_env: TEST_ASSISTANT_ID
retriever:
  candidate_limit: 3000
  latency_budget_ms: 120
  auto_by_budget: false
ui:
  skip_preflight: true
""",
        encoding="utf-8",
    )
    (repo_root / "VisionStatement.pdf").write_bytes(b"%PDF-1.4\n")
    return repo_root


def test_client_context_exposes_settings(
    repo_with_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo_with_config))
    ctx = ClientContext.load(slug=DUMMY_SLUG, require_env=False, interactive=False)
    assert isinstance(ctx.settings, Settings)
    assert ctx.settings.vision_model == "gpt-4o-mini-2024-07-18"
    assert ctx.settings.ui_skip_preflight is True
    assert ctx.settings.get_value("retriever.candidate_limit") == 3000
