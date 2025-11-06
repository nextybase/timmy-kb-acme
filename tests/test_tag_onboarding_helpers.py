# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import tag_onboarding_raw as raw_ingest
from tag_onboarding_raw import copy_from_local, download_from_drive
from timmykb.tag_onboarding import _should_proceed  # type: ignore


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *args, **kwargs):
        pass


def test_should_proceed_non_interactive_without_proceed_stops(tmp_path: Path) -> None:
    log = _NoopLogger()
    assert _should_proceed(non_interactive=True, proceed_after_csv=False, logger=log) is False


def test_should_proceed_non_interactive_with_proceed_continues(tmp_path: Path) -> None:
    log = _NoopLogger()
    assert _should_proceed(non_interactive=True, proceed_after_csv=True, logger=log) is True


def test_copy_from_local_skips_when_same_path(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    ctx = type("Ctx", (), {"slug": "x"})()

    calls = {"copied": 0}

    def _fake_copy(src, dst, logger):  # noqa: ANN001 ANN201
        calls["copied"] += 1
        return 0

    original = raw_ingest.copy_local_pdfs_to_raw
    raw_ingest.copy_local_pdfs_to_raw = _fake_copy  # type: ignore
    try:
        copy_from_local(
            _NoopLogger(),
            raw_dir=raw,
            local_path=str(raw),
            non_interactive=True,
            context=ctx,
        )  # no call
    finally:
        raw_ingest.copy_local_pdfs_to_raw = original  # type: ignore
    assert calls["copied"] == 0


def test_download_from_drive_invokes_download(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "kb"
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    ctx = type("Ctx", (), {"slug": "x"})()

    monkeypatch.setattr(raw_ingest, "get_client_config", lambda _c: {"drive_raw_folder_id": "fid123"}, raising=True)
    monkeypatch.setattr(raw_ingest, "get_drive_service", lambda _c: object(), raising=True)

    called = {"ok": False}

    def _fake_download(  # noqa: ANN001
        service, remote_root_folder_id, local_root_dir, progress, context, redact_logs, *, overwrite=False, **_
    ):
        assert remote_root_folder_id == "fid123"
        assert Path(local_root_dir) == raw
        called["ok"] = True

    monkeypatch.setattr(raw_ingest, "download_drive_pdfs_to_local", _fake_download, raising=True)
    download_from_drive(ctx, _NoopLogger(), raw_dir=raw, non_interactive=True)
    assert called["ok"] is True
