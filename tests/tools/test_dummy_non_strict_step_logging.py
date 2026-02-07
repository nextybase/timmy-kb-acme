# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tools.dummy import orchestrator


@pytest.fixture
def logger() -> logging.Logger:
    log = logging.getLogger("tests.dummy.non_strict_step")
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.INFO)
    return log


def test_non_strict_step_logs_slug(monkeypatch, caplog, tmp_path: Path, logger: logging.Logger) -> None:
    monkeypatch.setattr(orchestrator, "_audit_non_strict_step", lambda **_: None)
    caplog.set_level("INFO")

    slug = "dummy-slug"
    with orchestrator._non_strict_step("vision_enrichment", logger=logger, base_dir=tmp_path, slug=slug):
        pass

    start = [r for r in caplog.records if r.getMessage() == "tools.gen_dummy_kb.non_strict_step.start"]
    complete = [r for r in caplog.records if r.getMessage() == "tools.gen_dummy_kb.non_strict_step.complete"]

    assert len(start) == 1, "start log missing"
    assert len(complete) == 1, "complete log missing"
    assert getattr(start[0], "slug", None) == slug
    assert getattr(complete[0], "slug", None) == slug
