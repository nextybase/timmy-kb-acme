# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pipeline.context import ClientContext
from pipeline.workspace_bootstrap import bootstrap_client_workspace
from tools.dummy import orchestrator
from tools.dummy.orchestrator import validate_dummy_structure


@pytest.fixture
def logger() -> logging.Logger:
    log = logging.getLogger("test.dummy.hardcheck")
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.INFO)
    return log


def _write_required_dummy_files(workspace_root: Path) -> None:
    (workspace_root / "config").mkdir(parents=True, exist_ok=True)
    (workspace_root / "semantic").mkdir(parents=True, exist_ok=True)
    (workspace_root / "book").mkdir(parents=True, exist_ok=True)
    (workspace_root / "raw").mkdir(parents=True, exist_ok=True)

    (workspace_root / "config" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (workspace_root / "semantic" / "semantic_mapping.yaml").write_text("context: {}\n", encoding="utf-8")
    (workspace_root / "semantic" / "tags.db").write_bytes(b"")
    (workspace_root / "book" / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (workspace_root / "book" / "SUMMARY.md").write_text("* [Dummy](README.md)\n", encoding="utf-8")
    (workspace_root / "raw" / "sample.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")


def test_dummy_validate_structure_passes_when_cartelle_yaml_present(tmp_path: Path, logger: logging.Logger) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-hc"
    workspace_root = repo_root / "output" / f"timmy-kb-{slug}"
    context = ClientContext(
        slug=slug,
        repo_root_dir=workspace_root,
        config_path=workspace_root / "config" / "config.yaml",
    )
    layout = bootstrap_client_workspace(context)

    _write_required_dummy_files(layout.base_dir)
    (layout.semantic_dir / "cartelle_raw.yaml").write_text(
        "version: 1\nfolders:\n  - key: governance\n    title: Governance\n",
        encoding="utf-8",
    )

    validate_dummy_structure(layout.base_dir, logger)


def test_dummy_validate_structure_fails_when_cartelle_yaml_missing(tmp_path: Path, logger: logging.Logger) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-hc"
    workspace_root = repo_root / "output" / f"timmy-kb-{slug}"
    context = ClientContext(
        slug=slug,
        repo_root_dir=workspace_root,
        config_path=workspace_root / "config" / "config.yaml",
    )
    layout = bootstrap_client_workspace(context)

    _write_required_dummy_files(layout.base_dir)

    with pytest.raises(RuntimeError) as exc:
        validate_dummy_structure(layout.base_dir, logger)
    assert "cartelle_raw" in str(exc.value)


def test_deep_compiles_yaml_before_vision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    logger: logging.Logger,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    base_dir = tmp_path / "workspace"
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    order: list[str] = []

    def _compile(_pdf_path: Path, yaml_target: Path) -> None:
        order.append("compile")
        yaml_target.write_text("version: 1\n", encoding="utf-8")

    def _run_vision_with_timeout_fn(**_: object) -> tuple[bool, dict[str, object] | None]:
        order.append("run_vision")
        assert (base_dir / "config" / "visionstatement.yaml").exists()
        return True, None

    def _get_env_var(name: str, default: str | None = None) -> str | None:
        if name == "VISION_MODE":
            return "DEEP"
        return default

    monkeypatch.setattr(orchestrator, "compile_document_to_vision_yaml", _compile)

    payload = orchestrator.build_dummy_payload(
        slug="dummy",
        client_name="Dummy",
        enable_drive=False,
        enable_vision=True,
        enable_semantic=False,
        enable_enrichment=False,
        enable_preview=False,
        records_hint=None,
        deep_testing=False,
        logger=logger,
        repo_root=repo_root,
        ensure_local_workspace_for_ui=lambda **_: None,
        run_vision=lambda **_: None,
        get_env_var=_get_env_var,
        ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
        open_for_read_bytes_selfguard=lambda path: path.open("rb"),
        load_vision_template_sections=lambda: [],
        client_base=lambda _: base_dir,
        pdf_path=lambda _: base_dir / "config" / "VisionStatement.pdf",
        register_client_fn=lambda *_: None,
        ClientContext=None,
        get_client_config=None,
        ensure_drive_minimal_and_upload_config=None,
        build_drive_from_mapping=None,
        emit_readmes_for_raw=None,
        run_vision_with_timeout_fn=_run_vision_with_timeout_fn,
        load_mapping_categories_fn=lambda _: {"contracts": {"ambito": "Contracts", "descrizione": "", "keywords": []}},
        ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
        ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
        ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
        ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
        write_basic_semantic_yaml_fn=None,
        write_minimal_tags_raw_fn=lambda *_args, **_kwargs: base_dir / "semantic" / "tags_raw.json",
        validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
        call_drive_min_fn=lambda *_args, **_kwargs: None,
        call_drive_build_from_mapping_fn=lambda *_args, **_kwargs: None,
        call_drive_emit_readmes_fn=lambda *_args, **_kwargs: None,
    )

    assert payload["vision_used"] is True
    assert order == ["compile", "run_vision"]


def test_deep_testing_downgrades_vision_on_quota_and_still_runs_drive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    logger: logging.Logger,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    base_dir = tmp_path / "workspace"
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    def _compile(_pdf_path: Path, yaml_target: Path) -> None:
        yaml_target.write_text("version: 1\n", encoding="utf-8")

    def _run_vision_with_timeout_fn(**_: object) -> tuple[bool, dict[str, object] | None]:
        return False, {
            "error": "Error code: 429 insufficient_quota - check your plan and billing",
            "file_path": "",
        }

    def _get_env_var(name: str, default: str | None = None) -> str | None:
        if name == "VISION_MODE":
            return "DEEP"
        return default

    drive_calls = {"min": 0, "build": 0, "readmes": 0}

    def _call_drive_min_fn(*_args: object, **_kwargs: object) -> dict[str, Any]:
        drive_calls["min"] += 1
        return {"ok": True}

    def _call_drive_build_from_mapping_fn(*_args: object, **_kwargs: object) -> dict[str, Any]:
        drive_calls["build"] += 1
        return {"ok": True}

    def _call_drive_emit_readmes_fn(*_args: object, **_kwargs: object) -> dict[str, Any]:
        drive_calls["readmes"] += 1
        return {"ok": True}

    monkeypatch.setattr(orchestrator, "compile_document_to_vision_yaml", _compile)

    payload = orchestrator.build_dummy_payload(
        slug="dummy",
        client_name="Dummy",
        enable_drive=True,
        enable_vision=True,
        enable_semantic=True,
        enable_enrichment=False,
        enable_preview=False,
        records_hint=None,
        deep_testing=True,
        logger=logger,
        repo_root=repo_root,
        ensure_local_workspace_for_ui=lambda **_: None,
        run_vision=lambda **_: None,
        get_env_var=_get_env_var,
        ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
        open_for_read_bytes_selfguard=lambda path: path.open("rb"),
        load_vision_template_sections=lambda: [],
        client_base=lambda _: base_dir,
        pdf_path=lambda _: base_dir / "config" / "VisionStatement.pdf",
        register_client_fn=lambda *_: None,
        ClientContext=None,
        get_client_config=None,
        ensure_drive_minimal_and_upload_config=None,
        build_drive_from_mapping=None,
        emit_readmes_for_raw=None,
        run_vision_with_timeout_fn=_run_vision_with_timeout_fn,
        load_mapping_categories_fn=lambda _: {},
        ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
        ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
        ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
        ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
        write_basic_semantic_yaml_fn=lambda *_args, **_kwargs: {"categories": {"contracts": {}}},
        write_minimal_tags_raw_fn=lambda *_args, **_kwargs: base_dir / "semantic" / "tags_raw.json",
        validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
        call_drive_min_fn=_call_drive_min_fn,
        call_drive_build_from_mapping_fn=_call_drive_build_from_mapping_fn,
        call_drive_emit_readmes_fn=_call_drive_emit_readmes_fn,
    )

    vision_check = payload["health"]["external_checks"]["vision_hardcheck"]
    assert vision_check["ok"] is False
    assert "downgraded to smoke" in vision_check["details"].lower()
    assert "quota/billing" in vision_check["details"].lower()
    assert payload["health"]["external_checks"]["drive_hardcheck"]["ok"] is True
    assert any("downgraded to smoke" in err.lower() for err in payload["health"]["errors"])
    assert drive_calls == {"min": 1, "build": 1, "readmes": 1}


def test_deep_testing_non_quota_vision_failure_still_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    logger: logging.Logger,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    base_dir = tmp_path / "workspace"
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    def _compile(_pdf_path: Path, yaml_target: Path) -> None:
        yaml_target.write_text("version: 1\n", encoding="utf-8")

    def _run_vision_with_timeout_fn(**_: object) -> tuple[bool, dict[str, object] | None]:
        return False, {"error": "permission denied", "file_path": ""}

    def _get_env_var(name: str, default: str | None = None) -> str | None:
        if name == "VISION_MODE":
            return "DEEP"
        return default

    monkeypatch.setattr(orchestrator, "compile_document_to_vision_yaml", _compile)

    with pytest.raises(orchestrator.HardCheckError):
        orchestrator.build_dummy_payload(
            slug="dummy",
            client_name="Dummy",
            enable_drive=True,
            enable_vision=True,
            enable_semantic=False,
            enable_enrichment=False,
            enable_preview=False,
            records_hint=None,
            deep_testing=True,
            logger=logger,
            repo_root=repo_root,
            ensure_local_workspace_for_ui=lambda **_: None,
            run_vision=lambda **_: None,
            get_env_var=_get_env_var,
            ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
            open_for_read_bytes_selfguard=lambda path: path.open("rb"),
            load_vision_template_sections=lambda: [],
            client_base=lambda _: base_dir,
            pdf_path=lambda _: base_dir / "config" / "VisionStatement.pdf",
            register_client_fn=lambda *_: None,
            ClientContext=None,
            get_client_config=None,
            ensure_drive_minimal_and_upload_config=None,
            build_drive_from_mapping=None,
            emit_readmes_for_raw=None,
            run_vision_with_timeout_fn=_run_vision_with_timeout_fn,
            load_mapping_categories_fn=lambda _: {},
            ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
            ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
            ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
            ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
            write_basic_semantic_yaml_fn=None,
            write_minimal_tags_raw_fn=lambda *_args, **_kwargs: base_dir / "semantic" / "tags_raw.json",
            validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
            call_drive_min_fn=lambda *_args, **_kwargs: None,
            call_drive_build_from_mapping_fn=lambda *_args, **_kwargs: None,
            call_drive_emit_readmes_fn=lambda *_args, **_kwargs: None,
        )
