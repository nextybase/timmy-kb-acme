from __future__ import annotations

from pathlib import Path

import src.tag_onboarding as to
from src.tag_onboarding import _copy_from_local, _download_from_drive, _should_proceed  # type: ignore


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

    to.copy_local_pdfs_to_raw = _fake_copy  # type: ignore
    _copy_from_local(_NoopLogger(), raw_dir=raw, local_path=str(raw), non_interactive=True, context=ctx)  # no call
    assert calls["copied"] == 0


def test_download_from_drive_invokes_download(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "kb"
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    ctx = type("Ctx", (), {"slug": "x"})()

    monkeypatch.setattr(to, "get_client_config", lambda _c: {"drive_raw_folder_id": "fid123"}, raising=True)
    monkeypatch.setattr(to, "get_drive_service", lambda _c: object(), raising=True)

    called = {"ok": False}

    def _fake_download(service, remote_root_folder_id, local_root_dir, progress, context, redact_logs):  # noqa: ANN001
        assert remote_root_folder_id == "fid123"
        assert Path(local_root_dir) == raw
        called["ok"] = True

    monkeypatch.setattr(to, "download_drive_pdfs_to_local", _fake_download, raising=True)
    _download_from_drive(ctx, _NoopLogger(), raw_dir=raw, non_interactive=True)
    assert called["ok"] is True
