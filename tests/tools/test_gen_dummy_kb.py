# SPDX-License-Identifier: GPL-3.0-only
"""Test per gen_dummy_kb refactor (build_payload e parse_args)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from tools import gen_dummy_kb


def _setup_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")
    return repo_root


def test_build_payload_without_vision(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: None)
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "run_vision", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no vision")))
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]

    captured: dict[str, Any] = {}

    def _fake_write_basic(base_dir: Path, *, slug: str, client_name: str) -> dict[str, str]:
        captured["called"] = (base_dir, slug, client_name)
        return {}

    monkeypatch.setattr(gen_dummy_kb, "_write_basic_semantic_yaml", _fake_write_basic)
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_build_from_mapping", lambda *a, **k: {"done": True})

    payload = gen_dummy_kb.build_payload(
        slug="demo",
        client_name="Demo Spa",
        enable_drive=False,
        enable_vision=False,
        records_hint=None,
        logger=logging.getLogger("test-gen-dummy"),
    )

    assert payload["slug"] == "demo"
    assert payload["client_name"] == "Demo Spa"
    assert payload["drive_used"] is False
    assert payload["vision_used"] is False
    assert "called" in captured
    assert payload["drive_min"] == {}
    assert payload["drive_build"] == {}


def test_build_payload_with_drive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: None)
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(gen_dummy_kb, "_write_basic_semantic_yaml", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "run_vision", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no vision")))
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]

    def _fake_drive_min(*_: Any, **__: Any) -> dict[str, Any]:
        return {"folder": "id123"}

    def _fake_drive_build(*_: Any, **__: Any) -> dict[str, Any]:
        return {"downloaded": 5}

    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", _fake_drive_min)
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_build_from_mapping", _fake_drive_build)

    payload = gen_dummy_kb.build_payload(
        slug="demo",
        client_name="Demo Spa",
        enable_drive=True,
        enable_vision=False,
        records_hint="7",
        logger=logging.getLogger("test-gen-dummy"),
    )

    assert payload["drive_used"] is True
    assert payload["drive_min"] == {"folder": "id123"}
    assert payload["drive_build"] == {"downloaded": 5}


def test_parse_args_defaults() -> None:
    parsed = gen_dummy_kb.parse_args([])
    assert parsed.slug == "dummy"
    assert parsed.no_drive is False
    assert parsed.no_vision is False
