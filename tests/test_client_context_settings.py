# SPDX-License-Identifier: GPL-3.0-only
"""Tests per l'integrazione di ClientContext con Settings."""

from __future__ import annotations

import logging
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
meta:
  client_name: "Cliente Demo"
ui:
  skip_preflight: true
  allow_local_only: true
  admin_local_mode: false
ai:
  openai:
    timeout: 90
    max_retries: 3
    http2_enabled: false
  prototimmy:
    engine: assistants
    model: gpt-4.1
    assistant_id_env: TEST_PROTOTIMMY_ID
    use_kb: true
  vision:
    engine: assistant
    model: gpt-4o-mini-2024-07-18
    assistant_id_env: TEST_ASSISTANT_ID
    snapshot_retention_days: 30
pipeline:
  retriever:
    auto_by_budget: false
    throttle:
      candidate_limit: 3000
      latency_budget_ms: 120
      parallelism: 1
      sleep_ms_between_calls: 0
ops:
  log_level: DEBUG
""",
        encoding="utf-8",
    )
    (repo_root / "VisionStatement.pdf").write_bytes(b"%PDF-1.4\n")
    return repo_root


def test_client_context_exposes_settings(
    repo_with_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(repo_with_config))
    ctx = ClientContext.load(slug=DUMMY_SLUG, require_env=False)
    assert isinstance(ctx.settings, Settings)
    assert ctx.settings.vision_model == "gpt-4o-mini-2024-07-18"
    assert ctx.settings.ui_skip_preflight is True
    assert ctx.settings.retriever_throttle.candidate_limit == 3000
    assert "prototimmy" in ctx.settings.as_dict().get("ai", {})


def test_client_context_logger_respects_ops_level(
    repo_with_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(repo_with_config))
    ctx = ClientContext.load(slug=DUMMY_SLUG, require_env=False)
    logger = ctx.logger or ctx._get_logger()
    assert logger.level == logging.DEBUG
    handler_levels = {h.level for h in logger.handlers}
    assert handler_levels == {logging.DEBUG}
