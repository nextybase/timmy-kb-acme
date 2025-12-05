# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline.exceptions import ConfigError
from semantic import api as sem


def test_runner_for_slug_calls_gating(monkeypatch, tmp_path):
    called = {"slug": None}

    def _gating(slug: str) -> None:
        called["slug"] = slug

    def _ctx_factory(slug: str):
        return SimpleNamespace(base_dir=tmp_path)

    def _run_base(context, logger, slug=None, stage_wrapper=None):
        return tmp_path, [], []

    monkeypatch.setattr(sem, "run_semantic_pipeline", _run_base)

    sem.run_semantic_pipeline_for_slug(
        "acme",
        context_factory=_ctx_factory,
        gating=_gating,
    )

    assert called["slug"] == "acme"


def test_runner_for_slug_propagates_configerror(monkeypatch, tmp_path):
    def _gating(slug: str) -> None:
        raise ConfigError("Semantica non disponibile", slug=slug)

    def _ctx_factory(slug: str):
        return SimpleNamespace(base_dir=tmp_path)

    monkeypatch.setattr(
        sem,
        "run_semantic_pipeline",
        lambda ctx, logger, slug=None, stage_wrapper=None: (_ for _ in ()).throw(
            AssertionError("non dovrebbe arrivare qui")
        ),
    )

    with pytest.raises(ConfigError, match="Semantica non disponibile"):
        sem.run_semantic_pipeline_for_slug(
            "acme",
            context_factory=_ctx_factory,
            gating=_gating,
        )
