# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pytest

from pipeline.drive.download_steps import DriveCandidate, discover_candidates, emit_progress
from pipeline.exceptions import PipelineError


class _LoggerStub:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, Any] | None]] = []
        self.errors: list[tuple[str, dict[str, Any] | None]] = []

    def warning(self, event: str, *, extra: dict[str, Any] | None = None) -> None:
        self.warnings.append((event, extra))

    def error(self, event: str, *, extra: dict[str, Any] | None = None) -> None:
        self.errors.append((event, extra))


def test_discover_candidates_missing_name_or_id_aborts(tmp_path: Path) -> None:
    logger = _LoggerStub()

    def _list_pdfs(_service: Any, _folder_id: str) -> Iterable[dict[str, Any]]:
        return [{"id": "file-1"}]

    def _list_folders(_service: Any, _folder_id: str) -> Iterable[dict[str, Any]]:
        return []

    with pytest.raises(PipelineError):
        discover_candidates(
            service=object(),
            raw_folder_id="root",
            list_folders=_list_folders,
            list_pdfs=_list_pdfs,
            ensure_dest=lambda *_a: tmp_path / "raw" / "missing.pdf",
            base_dir=tmp_path,
            local_root=tmp_path / "raw",
            logger=logger,
        )

    assert any(event == "drive.candidate.invalid" for event, _ in logger.warnings)


def test_discover_candidates_ensure_dest_failure_aborts(tmp_path: Path) -> None:
    logger = _LoggerStub()

    def _list_pdfs(_service: Any, _folder_id: str) -> Iterable[dict[str, Any]]:
        return [{"id": "file-1", "name": "Report"}]

    def _list_folders(_service: Any, _folder_id: str) -> Iterable[dict[str, Any]]:
        return []

    def _ensure_dest(*_a: Any, **_k: Any) -> Path:
        raise RuntimeError("boom")

    with pytest.raises(PipelineError):
        discover_candidates(
            service=object(),
            raw_folder_id="root",
            list_folders=_list_folders,
            list_pdfs=_list_pdfs,
            ensure_dest=_ensure_dest,
            base_dir=tmp_path,
            local_root=tmp_path / "raw",
            logger=logger,
        )

    assert any(event == "drive.candidate.ensure_failed" for event, _ in logger.errors)


def test_emit_progress_callback_failure_aborts(tmp_path: Path) -> None:
    logger = _LoggerStub()
    candidate = DriveCandidate(
        category="",
        filename="doc.pdf",
        destination=tmp_path / "doc.pdf",
        remote_id="rid",
        remote_size=1,
        metadata={},
    )

    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("callback failed")

    with pytest.raises(PipelineError):
        emit_progress([candidate], _boom, logger=logger)

    assert any(event == "drive.progress_callback.failed" for event, _ in logger.errors)
