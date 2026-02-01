# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

import ui.services.drive as drive_service


def test_render_drive_tree_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_get_cache():
        calls["get_cache"] = True

        def inner(slug: str):
            calls["slug"] = slug
            return {"slug": {"id": "123"}}

        return inner

    monkeypatch.setattr(drive_service, "get_drive_tree_cache", fake_get_cache)

    result = drive_service.render_drive_tree("dummy")

    assert calls.get("get_cache") is True
    assert calls.get("slug") == "dummy"
    assert result == {"slug": {"id": "123"}}


def test_render_drive_diff_delegates_to_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get_cache():
        def inner(slug: str):
            captured["slug"] = slug
            return {"slug": {"files": []}}

        return inner

    def fake_diff(slug: str, index: dict) -> None:
        captured["diff"] = (slug, index)

    monkeypatch.setattr(drive_service, "get_drive_tree_cache", fake_get_cache)
    monkeypatch.setattr(drive_service, "_render_diff_component", fake_diff)

    drive_service.render_drive_diff("dummy")

    assert captured.get("slug") == "dummy"
    assert captured.get("diff") == ("dummy", {"slug": {"files": []}})


def test_render_drive_diff_handles_cache_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get_cache():
        raise RuntimeError("boom")

    def fake_diff(slug: str, index: dict) -> None:
        captured["diff"] = (slug, index)

    monkeypatch.setattr(drive_service, "get_drive_tree_cache", fake_get_cache)
    monkeypatch.setattr(drive_service, "_render_diff_component", fake_diff)

    drive_service.render_drive_diff("dummy")

    assert captured.get("diff") == ("dummy", {})


def test_invalidate_drive_index_clears_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {}

    def fake_clear():
        called["clear"] = True

    monkeypatch.setattr(drive_service, "_clear_drive_tree_cache", fake_clear)

    drive_service.invalidate_drive_index()

    assert called.get("clear") is True
