# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from ui.utils import slug as slug_mod


def test_runtime_slug_prefers_query(monkeypatch):
    monkeypatch.setattr(slug_mod, "_qp_get", lambda: " Acme-1 ")
    monkeypatch.setattr(slug_mod, "_current_session_slug", lambda: "sess-1")
    monkeypatch.setattr(slug_mod, "_load_persisted", lambda: "persist-1")
    assert slug_mod.get_runtime_slug() == "acme-1"


def test_runtime_slug_falls_back_to_session(monkeypatch):
    monkeypatch.setattr(slug_mod, "_qp_get", lambda: None)
    monkeypatch.setattr(slug_mod, "_current_session_slug", lambda: "sess-1")
    monkeypatch.setattr(slug_mod, "_load_persisted", lambda: "persist-1")
    assert slug_mod.get_runtime_slug() == "sess-1"


def test_runtime_slug_falls_back_to_persisted(monkeypatch):
    monkeypatch.setattr(slug_mod, "_qp_get", lambda: None)
    monkeypatch.setattr(slug_mod, "_current_session_slug", lambda: None)
    monkeypatch.setattr(slug_mod, "_load_persisted", lambda: "persist-1")
    assert slug_mod.get_runtime_slug() == "persist-1"


def test_runtime_slug_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(slug_mod, "_qp_get", lambda: None)
    monkeypatch.setattr(slug_mod, "_current_session_slug", lambda: None)
    monkeypatch.setattr(slug_mod, "_load_persisted", lambda: None)
    assert slug_mod.get_runtime_slug() is None
