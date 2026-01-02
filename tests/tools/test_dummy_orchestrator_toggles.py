# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from tools.dummy import orchestrator


@contextmanager
def _open_bytes(path: Path) -> Iterator[object]:
    with path.open("rb") as handle:
        yield handle


def _noop(*_args: object, **_kwargs: object) -> None:
    return None


def test_semantic_toggle_skips_artifact_calls(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    base_dir = tmp_path / "workspace"
    for child in ("raw", "semantic", "book", "config"):
        (base_dir / child).mkdir(parents=True, exist_ok=True)

    def _client_base(_slug: str) -> Path:
        return base_dir

    def _pdf_path(_slug: str) -> Path:
        return base_dir / "config" / "VisionStatement.pdf"

    def _get_env_var(_name: str, _default: str | None = None) -> str | None:
        return "SMOKE"

    def _raise_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("semantic step should be skipped")

    called = {"book": False}

    def _book_skeleton(_base_dir: Path) -> None:
        called["book"] = True

    payload = orchestrator.build_dummy_payload(
        slug="dummy",
        client_name="Dummy",
        enable_drive=False,
        enable_vision=False,
        enable_semantic=False,
        enable_enrichment=False,
        enable_preview=False,
        records_hint=None,
        deep_testing=False,
        logger=logging.getLogger("test.dummy.toggle"),
        repo_root=repo_root,
        ensure_local_workspace_for_ui=_noop,
        run_vision=_raise_if_called,
        get_env_var=_get_env_var,
        ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
        open_for_read_bytes_selfguard=_open_bytes,
        load_vision_template_sections=lambda: [],
        client_base=_client_base,
        pdf_path=_pdf_path,
        register_client_fn=_noop,
        ClientContext=None,
        get_client_config=None,
        ensure_drive_minimal_and_upload_config=None,
        build_drive_from_mapping=None,
        emit_readmes_for_raw=None,
        run_vision_with_timeout_fn=lambda **_: (_raise_if_called(), None),  # type: ignore[return-value]
        load_mapping_categories_fn=_raise_if_called,
        ensure_minimal_tags_db_fn=_raise_if_called,
        ensure_raw_pdfs_fn=_raise_if_called,
        ensure_local_readmes_fn=_raise_if_called,
        ensure_book_skeleton_fn=_book_skeleton,
        write_minimal_tags_raw_fn=_raise_if_called,
        validate_dummy_structure_fn=_raise_if_called,
    )

    assert payload["health"]["mode"] == "smoke"
    assert called["book"] is True
