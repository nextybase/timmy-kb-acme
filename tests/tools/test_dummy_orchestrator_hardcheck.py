# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

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
        base_dir=workspace_root,
        raw_dir=workspace_root / "raw",
        md_dir=workspace_root / "book",
        config_path=workspace_root / "config" / "config.yaml",
        output_dir=workspace_root,
    )
    layout = bootstrap_client_workspace(context)

    _write_required_dummy_files(layout.base_dir)
    (layout.semantic_dir / "cartelle_raw.yaml").write_text("folders: []\n", encoding="utf-8")

    validate_dummy_structure(layout.base_dir, logger)


def test_dummy_validate_structure_fails_when_cartelle_yaml_missing(tmp_path: Path, logger: logging.Logger) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-hc"
    workspace_root = repo_root / "output" / f"timmy-kb-{slug}"
    context = ClientContext(
        slug=slug,
        repo_root_dir=workspace_root,
        base_dir=workspace_root,
        raw_dir=workspace_root / "raw",
        md_dir=workspace_root / "book",
        config_path=workspace_root / "config" / "config.yaml",
        output_dir=workspace_root,
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
