# SPDX-License-Identifier: GPL-3.0-only
"""Test per gen_dummy_kb refactor (build_payload e parse_args)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pipeline.file_utils import safe_write_text
from tools import gen_dummy_kb
from tools.dummy import orchestrator


def _setup_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")
    return repo_root


def _seed_config(base_dir: Path) -> None:
    cfg_dir = base_dir / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    safe_write_text(cfg_dir / "config.yaml", "meta: {}\n", encoding="utf-8", atomic=True)


def test_repo_root_is_repo_root() -> None:
    repo_root = gen_dummy_kb.REPO_ROOT
    assert (repo_root / "pyproject.toml").exists()
    assert (repo_root / "tools").exists()


def test_build_payload_without_vision(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "logs").mkdir(parents=True, exist_ok=True)
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VISION_MODE", "SMOKE")

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: _seed_config(workspace))
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]
    monkeypatch.setattr(orchestrator, "pre_onboarding_main", lambda **_: None)
    monkeypatch.setattr(orchestrator, "run_raw_ingest", lambda **_: None)
    monkeypatch.setattr(orchestrator, "semantic_convert_markdown", lambda *_, **__: None)
    monkeypatch.setattr(orchestrator, "semantic_write_summary_and_readme", lambda *_, **__: None)
    monkeypatch.setattr(
        orchestrator,
        "PipelineClientContext",
        type(
            "DummyCtx",
            (),
            {
                "load": staticmethod(
                    lambda **__: type("Ctx", (), {"logs_dir": workspace / "logs", "log_dir": workspace / "logs"})()
                )
            },
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "WorkspaceLayout",
        type(
            "DummyWL",
            (),
            {"from_context": staticmethod(lambda _ctx: type("Layout", (), {"logs_dir": workspace / "logs"})())},
        ),
    )

    monkeypatch.setattr(
        gen_dummy_kb,
        "_run_vision_with_timeout",
        lambda **_: (_ for _ in ()).throw(AssertionError("vision non dovrebbe essere chiamata")),
    )
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {"ok": True})
    original_validate = gen_dummy_kb._validate_dummy_structure
    called = False

    def _tracked_validate(base_dir: Path, logger: logging.Logger) -> None:
        nonlocal called
        called = True
        original_validate(base_dir, logger)

    monkeypatch.setattr(gen_dummy_kb, "_validate_dummy_structure", _tracked_validate)

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
    assert payload["drive_min"] == {}
    assert "fallback_used" not in payload
    assert isinstance(payload["local_readmes"], list)
    assert "health" in payload
    assert isinstance(payload["health"].get("readmes_count"), int)
    assert (workspace / "semantic" / "semantic_mapping.yaml").exists()
    assert (workspace / "semantic" / "tags.db").exists()
    assert (workspace / "book" / "README.md").exists()
    assert (workspace / "book" / "SUMMARY.md").exists()
    assert any((workspace / "raw").rglob("*.pdf"))
    assert called is True


def test_build_payload_with_drive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VISION_MODE", "SMOKE")

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: _seed_config(workspace))
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]
    monkeypatch.setattr(orchestrator, "pre_onboarding_main", lambda **_: None)
    monkeypatch.setattr(orchestrator, "run_raw_ingest", lambda **_: None)
    monkeypatch.setattr(orchestrator, "semantic_convert_markdown", lambda *_, **__: None)
    monkeypatch.setattr(orchestrator, "semantic_write_summary_and_readme", lambda *_, **__: None)
    monkeypatch.setattr(
        orchestrator,
        "PipelineClientContext",
        type(
            "DummyCtx",
            (),
            {
                "load": staticmethod(
                    lambda **__: type("Ctx", (), {"logs_dir": workspace / "logs", "log_dir": workspace / "logs"})()
                )
            },
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "WorkspaceLayout",
        type(
            "DummyWL",
            (),
            {"from_context": staticmethod(lambda _ctx: type("Layout", (), {"logs_dir": workspace / "logs"})())},
        ),
    )

    def _fake_drive_min(*_: Any, **__: Any) -> dict[str, Any]:
        return {"folder": "id123"}

    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", _fake_drive_min)
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
    assert payload["drive_readmes"] == {"uploaded": 2}
    assert "fallback_used" not in payload
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
    (workspace / "logs").mkdir(parents=True, exist_ok=True)
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    semantic_dir = workspace / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    (workspace / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")
    monkeypatch.setenv("VISION_MODE", "DEEP")

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: _seed_config(workspace))
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(orchestrator, "pre_onboarding_main", lambda **_: None)
    monkeypatch.setattr(orchestrator, "run_raw_ingest", lambda **_: None)
    monkeypatch.setattr(orchestrator, "semantic_convert_markdown", lambda *_, **__: None)
    monkeypatch.setattr(orchestrator, "semantic_write_summary_and_readme", lambda *_, **__: None)
    monkeypatch.setattr(
        orchestrator,
        "PipelineClientContext",
        type(
            "DummyCtx",
            (),
            {
                "load": staticmethod(
                    lambda **__: type("Ctx", (), {"logs_dir": workspace / "logs", "log_dir": workspace / "logs"})()
                )
            },
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "WorkspaceLayout",
        type(
            "DummyWL",
            (),
            {"from_context": staticmethod(lambda _ctx: type("Layout", (), {"logs_dir": workspace / "logs"})())},
        ),
    )
    monkeypatch.setattr(
        gen_dummy_kb,
        "_run_vision_with_timeout",
        lambda **_: (_ for _ in ()).throw(AssertionError("vision non dovrebbe essere chiamata")),
    )
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_kb, "_validate_dummy_structure", lambda *a, **k: None)

    sentinel_path = workspace / "config" / ".vision_hash"

    def _fake_run_vision(**_: Any) -> tuple[bool, dict[str, Any]]:
        return True, {
            "already_done": True,
            "message": "Vision già eseguito per questo PDF.",
            "file_path": str(sentinel_path),
        }

    monkeypatch.setattr(gen_dummy_kb, "_run_vision_with_timeout", lambda **kwargs: _fake_run_vision(**kwargs))
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]
    monkeypatch.setattr(
        orchestrator,
        "compile_document_to_vision_yaml",
        lambda _pdf, target: target.write_text("version: 1\n", encoding="utf-8"),
    )

    payload = gen_dummy_kb.build_payload(
        slug="dummy",
        client_name="Dummy Spa",
        enable_drive=False,
        enable_vision=True,
        records_hint=None,
        logger=logging.getLogger("test-gen-dummy"),
    )

    assert payload["vision_used"] is True
    assert "fallback_used" not in payload


def test_build_payload_does_not_register_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "logs").mkdir(parents=True, exist_ok=True)
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    (workspace / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")
    monkeypatch.setenv("VISION_MODE", "SMOKE")

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: _seed_config(workspace))
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(orchestrator, "pre_onboarding_main", lambda **_: None)
    monkeypatch.setattr(orchestrator, "run_raw_ingest", lambda **_: None)
    monkeypatch.setattr(orchestrator, "_ensure_spacy_available", lambda policy: None)
    monkeypatch.setattr(orchestrator, "semantic_convert_markdown", lambda *_, **__: None)
    monkeypatch.setattr(orchestrator, "semantic_write_summary_and_readme", lambda *_, **__: None)
    monkeypatch.setattr(
        orchestrator,
        "PipelineClientContext",
        type(
            "DummyCtx",
            (),
            {
                "load": staticmethod(
                    lambda **__: type("Ctx", (), {"logs_dir": workspace / "logs", "log_dir": workspace / "logs"})()
                )
            },
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "WorkspaceLayout",
        type(
            "DummyWL",
            (),
            {"from_context": staticmethod(lambda _ctx: type("Layout", (), {"logs_dir": workspace / "logs"})())},
        ),
    )
    monkeypatch.setattr(
        gen_dummy_kb,
        "_run_vision_with_timeout",
        lambda **_: (True, None),
    )
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {})
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


def test_build_payload_smoke_writes_minimal_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "logs").mkdir(parents=True, exist_ok=True)
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    (workspace / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")
    monkeypatch.setenv("VISION_MODE", "SMOKE")

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: _seed_config(workspace))
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(orchestrator, "pre_onboarding_main", lambda **_: None)
    monkeypatch.setattr(orchestrator, "run_raw_ingest", lambda **_: None)
    monkeypatch.setattr(orchestrator, "_ensure_spacy_available", lambda policy: None)
    monkeypatch.setattr(orchestrator, "semantic_convert_markdown", lambda *_, **__: None)
    monkeypatch.setattr(orchestrator, "semantic_write_summary_and_readme", lambda *_, **__: None)
    monkeypatch.setattr(
        orchestrator,
        "PipelineClientContext",
        type(
            "DummyCtx",
            (),
            {
                "load": staticmethod(
                    lambda **__: type("Ctx", (), {"logs_dir": workspace / "logs", "log_dir": workspace / "logs"})()
                )
            },
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "WorkspaceLayout",
        type(
            "DummyWL",
            (),
            {"from_context": staticmethod(lambda _ctx: type("Layout", (), {"logs_dir": workspace / "logs"})())},
        ),
    )
    monkeypatch.setattr(
        gen_dummy_kb,
        "_run_vision_with_timeout",
        lambda **_: (_ for _ in ()).throw(AssertionError("vision non dovrebbe essere chiamata")),
    )
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {})
    original_validate = gen_dummy_kb._validate_dummy_structure
    called = False

    def _tracked_validate(base_dir: Path, logger: logging.Logger) -> None:
        nonlocal called
        called = True
        original_validate(base_dir, logger)

    monkeypatch.setattr(gen_dummy_kb, "_validate_dummy_structure", _tracked_validate)

    payload = gen_dummy_kb.build_payload(
        slug="dummy",
        client_name="Dummy Spa",
        enable_drive=False,
        enable_vision=False,
        records_hint=None,
        logger=logging.getLogger("test-gen-dummy"),
    )

    assert payload["vision_used"] is False
    assert "fallback_used" not in payload
    assert (workspace / "semantic" / "semantic_mapping.yaml").exists()
    assert (workspace / "semantic" / "tags.db").exists()
    assert (workspace / "book" / "README.md").exists()
    assert (workspace / "book" / "SUMMARY.md").exists()
    assert any((workspace / "raw").rglob("*.pdf"))
    assert called is True


def test_build_payload_deep_fails_on_vision_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VISION_MODE", "DEEP")

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_local_workspace_for_ui", lambda **_: _seed_config(workspace))
    monkeypatch.setattr(gen_dummy_kb, "_client_base", lambda slug: workspace)
    monkeypatch.setattr(gen_dummy_kb, "_pdf_path", lambda slug: workspace / "config" / "VisionStatement.pdf")
    monkeypatch.setattr(gen_dummy_kb, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_kb, "ClientContext", None)
    monkeypatch.setattr(gen_dummy_kb, "get_client_config", lambda *_: {})  # type: ignore[misc]
    monkeypatch.setattr(
        orchestrator,
        "compile_document_to_vision_yaml",
        lambda _pdf, target: target.write_text("version: 1\n", encoding="utf-8"),
    )
    monkeypatch.setattr(
        gen_dummy_kb,
        "_run_vision_with_timeout",
        lambda **_: (False, {"error": "boom"}),
    )
    monkeypatch.setattr(gen_dummy_kb, "_call_drive_min", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_kb, "_validate_dummy_structure", lambda *a, **k: None)
    monkeypatch.setattr(
        gen_dummy_kb,
        "_build_dummy_payload",
        gen_dummy_kb._build_dummy_payload,
    )
    monkeypatch.setattr(
        gen_dummy_kb,
        "build_payload",
        gen_dummy_kb.build_payload,
    )

    with pytest.raises(gen_dummy_kb.HardCheckError):
        gen_dummy_kb.build_payload(
            slug="dummy",
            client_name="Dummy Spa",
            enable_drive=False,
            enable_vision=True,
            records_hint=None,
            logger=logging.getLogger("test-gen-dummy"),
        )


def test_main_brute_reset_deletes_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _setup_repo_root(tmp_path)
    output_dir = repo_root / "output" / "timmy-kb-dummy"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_write_text(output_dir / "marker.txt", "cleanup", encoding="utf-8", atomic=True)

    monkeypatch.setattr(gen_dummy_kb, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gen_dummy_kb, "ensure_dotenv_loaded", lambda: None)

    def _unexpected(*_: Any, **__: Any) -> None:
        raise AssertionError("generation should not run during brute reset")

    monkeypatch.setattr(gen_dummy_kb, "build_payload", _unexpected)

    exit_code = gen_dummy_kb.main(["--slug", "dummy", "--brute-reset"])

    assert exit_code == 0
    assert not output_dir.exists()
