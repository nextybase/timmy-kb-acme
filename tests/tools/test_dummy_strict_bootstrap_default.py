# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from pipeline.exceptions import ConfigError
from tests._helpers.workspace_paths import local_workspace_dir
from tools.dummy import orchestrator


def _workspace_env_setter(base_dir: Path):
    def _setter(*, slug: str, client_name: str, vision_statement_pdf: bytes | None) -> None:
        pass

    return _setter


def test_vision_strict_output_bootstrap_default(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-bootstrap"
    workspace_base = local_workspace_dir(repo_root / "output", slug)

    call_count = 0

    def fake_load(*, slug: str, require_env: bool, run_id: str | None, bootstrap_config: bool):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConfigError("context missing", slug=slug)
        return SimpleNamespace(
            slug=slug,
            repo_root_dir=workspace_base,
            config_path=workspace_base / "config" / "config.yaml",
        )

    monkeypatch.setattr(orchestrator.PipelineClientContext, "load", fake_load)
    monkeypatch.setattr(orchestrator, "update_config_with_drive_ids", lambda *args, **kwargs: None)
    decisions = orchestrator.build_dummy_payload(
        slug=slug,
        client_name="Dummy",
        enable_drive=False,
        allow_local_only_override=False,
        enable_vision=False,
        enable_semantic=False,
        enable_enrichment=False,
        enable_preview=False,
        records_hint=None,
        deep_testing=False,
        logger=logging.getLogger("tests.dummy.strict"),
        repo_root=repo_root,
        ensure_local_workspace_for_ui=_workspace_env_setter(workspace_base),
        run_vision=lambda **_: None,
        get_env_var=lambda *_: None,
        ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
        open_for_read_bytes_selfguard=lambda path: path.open("rb"),
        load_vision_template_sections=lambda: [],
        client_base=lambda _: workspace_base,
        pdf_path=lambda _: workspace_base / "config" / "VisionStatement.pdf",
        register_client_fn=lambda *_args, **_kwargs: None,
        ClientContext=orchestrator.PipelineClientContext,
        get_client_config=None,
        ensure_drive_minimal_and_upload_config=None,
        emit_readmes_for_raw=None,
        run_vision_with_timeout_fn=lambda **_: (True, None),
        load_mapping_categories_fn=lambda *_args, **_kwargs: {},
        ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
        ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
        ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
        ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
        write_basic_semantic_yaml_fn=None,
        write_minimal_tags_raw_fn=lambda *_args, **_kwargs: workspace_base / "semantic" / "tags_raw.json",
        validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
        ensure_spacy_available_fn=lambda policy: None,
        call_drive_min_fn=lambda *_args, **_kwargs: None,
        call_drive_emit_readmes_fn=lambda *_args, **_kwargs: None,
    )["decisions"]["vision_strict_output"]

    assert decisions["effective"] is True
    assert decisions["source"] == "bootstrap_default"
    assert decisions["rationale"] == "default_true_bootstrap_phase"
