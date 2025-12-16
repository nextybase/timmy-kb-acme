# SPDX-License-Identifier: GPL-3.0-only
"""Test per gen_dummy_kb refactor (build_payload e parse_args)."""

from __future__ import annotations

import logging
import sys
import types
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
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]

    captured: dict[str, Any] = {}

    def _fake_write_basic(base_dir: Path, *, slug: str, client_name: str) -> dict[str, str]:
        captured["called"] = (base_dir, slug, client_name)
        return {"categories": {}}

    monkeypatch.setattr(
        gen_dummy_kb,
        "_run_vision_with_timeout",
        lambda **_: (_ for _ in ()).throw(AssertionError("vision non dovrebbe essere chiamata")),
    )
    monkeypatch.setattr(gen_dummy_kb, "_write_basic_semantic_yaml", _fake_write_basic)
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_build_from_mapping", lambda *a, **k: {"done": True})
    monkeypatch.setattr(gen_dummy_kb, "_validate_dummy_structure", lambda *a, **k: None)

    payload = gen_dummy_kb.build_payload(
        slug="dummy",
        client_name="Dummy Spa",
        enable_drive=False,
        enable_vision=False,
        records_hint=None,
        logger=logging.getLogger("test-gen-dummy"),
    )

    assert payload["slug"] == "dummy"
    assert payload["client_name"] == "Dummy Spa"
    assert payload["drive_used"] is False
    assert payload["vision_used"] is False
    assert "called" in captured
    assert payload["drive_min"] == {}
    assert payload["drive_build"] == {}
    assert payload["fallback_used"] is True
    assert isinstance(payload["local_readmes"], list)
    assert "health" in payload
    assert isinstance(payload["health"].get("readmes_count"), int)


def test_build_payload_with_drive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: None)
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(gen_dummy_kb, "_write_basic_semantic_yaml", lambda *a, **k: {"categories": {}})
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]

    def _fake_drive_min(*_: Any, **__: Any) -> dict[str, Any]:
        return {"folder": "id123"}

    def _fake_drive_build(*_: Any, **__: Any) -> dict[str, Any]:
        return {"downloaded": 5}

    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", _fake_drive_min)
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_build_from_mapping", _fake_drive_build)
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_emit_readmes", lambda *a, **k: {"uploaded": 2})
    monkeypatch.setattr(gen_dummy_kb, "_validate_dummy_structure", lambda *a, **k: None)

    payload = gen_dummy_kb.build_payload(
        slug="dummy",
        client_name="Dummy Spa",
        enable_drive=True,
        enable_vision=False,
        records_hint="7",
        logger=logging.getLogger("test-gen-dummy"),
    )

    assert payload["drive_used"] is True
    assert payload["vision_used"] is False
    assert payload["drive_min"] == {"folder": "id123"}
    assert payload["drive_build"] == {"downloaded": 5}
    assert payload["drive_readmes"] == {"uploaded": 2}
    assert payload["fallback_used"] is True
    assert isinstance(payload["local_readmes"], list)


def test_parse_args_defaults() -> None:
    parsed = gen_dummy_kb.parse_args([])
    assert parsed.slug == "dummy"
    assert parsed.no_drive is False
    assert parsed.no_vision is False


def test_build_payload_skips_vision_if_already_done(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    semantic_dir = workspace / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: None)
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(
        gen_dummy_kb,
        "_run_vision_with_timeout",
        lambda **_: (_ for _ in ()).throw(AssertionError("vision non dovrebbe essere chiamata")),
    )
    monkeypatch.setattr(gen_dummy_kb, "_write_basic_semantic_yaml", lambda *a, **k: {"categories": {}})
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_build_from_mapping", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_kb, "_validate_dummy_structure", lambda *a, **k: None)

    sentinel_path = workspace / "config" / ".vision_hash"

    def _fake_run_vision(**_: Any) -> tuple[bool, dict[str, Any]]:
        return False, {
            "error": "Vision già eseguito per questo PDF.",
            "file_path": str(sentinel_path),
        }

    monkeypatch.setattr(gen_dummy_kb, "_run_vision_with_timeout", lambda **kwargs: _fake_run_vision(**kwargs))
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]

    payload = gen_dummy_kb.build_payload(
        slug="dummy",
        client_name="Dummy Spa",
        enable_drive=False,
        enable_vision=True,
        records_hint=None,
        logger=logging.getLogger("test-gen-dummy"),
    )

    assert payload["vision_used"] is True
    assert payload["fallback_used"] is False


def test_build_payload_does_not_register_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: None)
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(
        gen_dummy_kb,
        "_run_vision_with_timeout",
        lambda **_: (True, None),
    )
    monkeypatch.setattr(gen_dummy_kb, "_write_basic_semantic_yaml", lambda *a, **k: {"categories": {}})
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_build_from_mapping", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_kb, "run_vision", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]
    monkeypatch.setattr(gen_dummy_kb, "_validate_dummy_structure", lambda *a, **k: None)

    called = False

    def _tracker(*_: Any, **__: Any) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(gen_dummy_kb, "_register_client", _tracker)

    gen_dummy_kb.build_payload(
        slug="dummy",
        client_name="Dummy Spa",
        enable_drive=False,
        enable_vision=False,
        records_hint=None,
        logger=logging.getLogger("test-gen-dummy"),
    )

    assert called is True


def test_main_triggers_cleanup_before_build(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_dotenv_loaded", lambda: None)
    monkeypatch.setitem(sys.modules, "ui.utils.workspace", types.SimpleNamespace(clear_base_cache=lambda **_: None))

    calls: list[str] = []

    def _fake_cleanup(slug: str, client_name: str, logger: logging.Logger) -> None:
        calls.append("cleanup")

    def _fake_build_payload(
        *,
        slug: str,
        client_name: str,
        enable_drive: bool,
        enable_vision: bool,
        records_hint: str | None,
        logger: logging.Logger,
        deep_testing: bool = False,
    ) -> dict[str, Any]:
        calls.append("build")
        return {"slug": slug, "client_name": client_name}

    monkeypatch.setattr(gen_dummy_kb, "_purge_previous_state", _fake_cleanup)
    monkeypatch.setattr(gen_dummy_kb, "build_payload", _fake_build_payload)
    monkeypatch.setattr(gen_dummy_kb, "emit_structure", lambda payload, stream=sys.stdout: calls.append("emit"))

    exit_code = gen_dummy_kb.main(["--slug", "dummy", "--no-drive", "--no-vision", "--base-dir", str(tmp_path)])

    assert exit_code == 0
    assert calls[:2] == ["cleanup", "build"]
