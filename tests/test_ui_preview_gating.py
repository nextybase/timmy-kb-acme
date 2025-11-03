# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pytest

import ui.gating as gating
from ui.gating import GateState, PagePaths, PageSpec, visible_page_specs


@pytest.fixture(autouse=True)
def _reset_gating_caches() -> None:
    gating.reset_gating_cache()


def _fake_page_specs() -> dict[str, Sequence[PageSpec]]:
    return {
        "Onboarding": (
            PageSpec(PagePaths.SEMANTICS, "Semantica", "/semantics"),
            PageSpec(PagePaths.PREVIEW, "Preview", "/preview"),
        )
    }


@dataclass
class _Env:
    raw_ready: bool
    state: str


def _setup_environment(monkeypatch: pytest.MonkeyPatch, env: _Env) -> None:
    slug = "acme"
    monkeypatch.setattr("ui.gating.get_active_slug", lambda: slug, raising=False)
    monkeypatch.setattr("ui.gating.has_raw_pdfs", lambda _slug: (env.raw_ready, None), raising=False)
    monkeypatch.setattr("ui.gating.get_state", lambda _slug: env.state, raising=False)
    monkeypatch.setattr("ui.gating.page_specs", _fake_page_specs, raising=False)


def _collect_paths(result: dict[str, Sequence[PageSpec]]) -> set[str]:
    return {spec.path for specs in result.values() for spec in specs}


def test_preview_hidden_when_raw_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_environment(monkeypatch, _Env(raw_ready=False, state="semantic_pending"))
    paths = _collect_paths(visible_page_specs(GateState(True, True, True)))
    assert PagePaths.SEMANTICS not in paths
    assert PagePaths.PREVIEW not in paths


def test_preview_hidden_until_state_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_environment(monkeypatch, _Env(raw_ready=True, state="in-progress"))
    paths = _collect_paths(visible_page_specs(GateState(True, True, True)))
    assert PagePaths.SEMANTICS in paths
    assert PagePaths.PREVIEW not in paths


def test_preview_visible_when_raw_and_state_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_environment(monkeypatch, _Env(raw_ready=True, state="arricchito"))
    paths = _collect_paths(visible_page_specs(GateState(True, True, True)))
    assert {PagePaths.SEMANTICS, PagePaths.PREVIEW}.issubset(paths)
