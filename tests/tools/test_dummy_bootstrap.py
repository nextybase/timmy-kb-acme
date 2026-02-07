# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

import pytest

from tests._helpers.workspace_paths import local_workspace_dir
from tools.dummy import orchestrator


def _workspace_env_setter(base_dir: Path) -> Callable[..., None]:
    def _setter(*, slug: str, client_name: str, vision_statement_pdf: bytes | None) -> None:
        os.environ["WORKSPACE_ROOT_DIR"] = str(base_dir)

    return _setter


@pytest.fixture
def logger() -> logging.Logger:
    log = logging.getLogger("tests.dummy.bootstrap")
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.INFO)
    return log


def test_dummy_bootstrap_records_event(monkeypatch, tmp_path: Path, logger: logging.Logger) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-bootstrap"
    workspace_base = local_workspace_dir(repo_root / "output", slug)

    captured: list[dict[str, object]] = []
    layout_marker = object()
    expected_slug = slug

    class DummyConn:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    conn = DummyConn()

    def _fake_resolve_workspace_layout(*, base_dir: Path, slug: str) -> object:
        assert base_dir == workspace_base
        assert slug == expected_slug
        return layout_marker

    monkeypatch.setattr(orchestrator, "_resolve_workspace_layout", _fake_resolve_workspace_layout)
    monkeypatch.setattr(orchestrator.decision_ledger, "open_ledger", lambda layout: conn)

    def _fake_record_event(
        conn_arg: DummyConn,
        *,
        event_id: str | None = None,
        slug: str,
        event_name: str,
        actor: str,
        occurred_at: str,
        payload: dict[str, object],
        **_: object,
    ) -> None:
        assert conn_arg is conn
        assert conn.closed is False
        captured.append(
            {
                "slug": slug,
                "event_name": event_name,
                "actor": actor,
                "payload": payload,
            }
        )

    monkeypatch.setattr(orchestrator.decision_ledger, "record_event", _fake_record_event)
    monkeypatch.setattr(
        orchestrator,
        "pre_onboarding_main",
        lambda **_: pytest.fail("pre_onboarding should not run"),
        raising=False,
    )

    payload = orchestrator.build_dummy_payload(
        slug=slug,
        client_name="Dummy Co.",
        enable_drive=False,
        allow_local_only_override=False,
        enable_vision=False,
        enable_semantic=False,
        enable_enrichment=False,
        enable_preview=False,
        records_hint=None,
        deep_testing=False,
        logger=logger,
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
        ClientContext=None,
        get_client_config=None,
        ensure_drive_minimal_and_upload_config=None,
        emit_readmes_for_raw=None,
        run_vision_with_timeout_fn=lambda **_: (True, None),
        load_mapping_categories_fn=lambda *_, **__: {},
        ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
        ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
        ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
        ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
        write_basic_semantic_yaml_fn=None,
        write_minimal_tags_raw_fn=lambda *_args, **_kwargs: workspace_base / "semantic" / "tags_raw.json",
        validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
        ensure_spacy_available_fn=lambda policy: None,
        call_drive_min_fn=lambda *_args, **_kwargs: None,
    )

    assert payload["slug"] == slug
    assert conn.closed
    assert len(captured) == 1
    event = captured[0]
    assert event["event_name"] == "dummy_bootstrap"
    assert event["actor"] == "dummy_pipeline"
    assert event["payload"]["slug"] == slug
    assert event["payload"]["stage"] == "skeleton"
    assert event["payload"]["enable_drive"] is False
    assert event["payload"]["enable_preview"] is False
    assert payload["paths"]["base"].endswith(str(workspace_base))


def test_dummy_bootstrap_loads_context_exactly_once(monkeypatch, tmp_path: Path, logger: logging.Logger) -> None:
    """
    Contratto Beta 1.0:
    - Dummy bootstrap deve caricare ClientContext una sola volta (post-skeleton),
      riusandolo per precheck + config update.
    """
    # cspell:ignore precheck

    calls: list[str | None] = []

    real_load = orchestrator.PipelineClientContext.load

    def _counting_load(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs.get("stage"))
        return real_load(*args, **kwargs)

    monkeypatch.setattr(orchestrator.PipelineClientContext, "load", _counting_load)

    orchestrator.build_dummy_payload(
        slug="dummy-bootstrap",
        client_name="Dummy Co.",
        enable_drive=False,
        allow_local_only_override=False,
        enable_vision=False,
        enable_semantic=False,
        enable_enrichment=False,
        enable_preview=False,
        records_hint=None,
        deep_testing=False,
        logger=logger,
        repo_root=tmp_path,
        ensure_local_workspace_for_ui=lambda **_: None,
        run_vision=lambda **_: None,
        get_env_var=lambda *_: None,
        ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
        open_for_read_bytes_selfguard=lambda path: path.open("rb"),
        load_vision_template_sections=lambda: [],
        client_base=lambda _: tmp_path,
        pdf_path=lambda _: tmp_path / "config" / "VisionStatement.pdf",
        register_client_fn=lambda *_a, **_k: None,
        ClientContext=orchestrator.PipelineClientContext,
        get_client_config=None,
        ensure_drive_minimal_and_upload_config=None,
        emit_readmes_for_raw=None,
        run_vision_with_timeout_fn=lambda **_: (True, None),
        load_mapping_categories_fn=lambda *_, **__: {},
        ensure_minimal_tags_db_fn=lambda *_a, **_k: None,
        ensure_raw_pdfs_fn=lambda *_a, **_k: None,
        ensure_local_readmes_fn=lambda *_a, **_k: [],
        ensure_book_skeleton_fn=lambda *_a, **_k: None,
        write_basic_semantic_yaml_fn=None,
        write_minimal_tags_raw_fn=lambda *_a, **_k: tmp_path / "semantic" / "tags_raw.json",
        validate_dummy_structure_fn=lambda *_a, **_k: None,
        ensure_spacy_available_fn=lambda policy: None,
        call_drive_min_fn=lambda *_a, **_k: None,
    )

    assert calls == [orchestrator._CTX_STAGE_POST_SKELETON]
