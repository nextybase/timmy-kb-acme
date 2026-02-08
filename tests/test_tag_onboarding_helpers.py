# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.ingest import provider as ingest_provider
from timmy_kb.cli import tag_onboarding
from timmy_kb.cli import tag_onboarding_raw as raw_ingest
from timmy_kb.cli.tag_onboarding import _should_proceed  # type: ignore
from timmy_kb.cli.tag_onboarding import run_nlp_to_db, scan_normalized_to_db
from timmy_kb.cli.tag_onboarding_raw import copy_from_local, download_from_drive


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *args, **kwargs):
        pass


@pytest.mark.parametrize(
    ("proceed_after_csv", "expected"),
    (
        (False, False),
        (True, True),
    ),
)
def test_should_proceed_non_interactive_flags(proceed_after_csv: bool, expected: bool) -> None:
    log = _NoopLogger()
    assert _should_proceed(non_interactive=True, proceed_after_csv=proceed_after_csv, logger=log) is expected


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

    monkeypatch.setattr(
        raw_ingest,
        "get_client_config",
        lambda _c: {"integrations": {"drive": {"raw_folder_id": "fid123"}}},
        raising=True,
    )
    monkeypatch.setattr(
        ingest_provider,
        "get_client_config",
        lambda _c: {"integrations": {"drive": {"raw_folder_id": "fid123"}}},
        raising=True,
    )
    monkeypatch.setattr(raw_ingest, "get_drive_service", lambda _c: object(), raising=True)

    called = {"ok": False}

    def _fake_download(  # noqa: ANN001
        service, remote_root_folder_id, local_root_dir, progress, context, redact_logs, *, overwrite=False, **_
    ):
        assert remote_root_folder_id == "fid123"
        assert Path(local_root_dir) == raw
        called["ok"] = True

    monkeypatch.setattr(raw_ingest, "download_drive_pdfs_to_local", _fake_download, raising=True)
    monkeypatch.setattr(
        ingest_provider,
        "get_drive_service",
        lambda _c: object(),
        raising=False,
    )
    monkeypatch.setattr(
        ingest_provider,
        "download_drive_pdfs_to_local",
        _fake_download,
        raising=False,
    )
    download_from_drive(ctx, _NoopLogger(), raw_dir=raw, non_interactive=True)
    assert called["ok"] is True


def _ensure_dirs(tmp_path: Path) -> tuple[Path, Path]:
    normalized = tmp_path / "workspace" / "normalized"
    semantic = tmp_path / "workspace" / "semantic"
    normalized.mkdir(parents=True, exist_ok=True)
    semantic.mkdir(parents=True, exist_ok=True)
    return normalized, semantic


def test_scan_normalized_strict_requires_repo_root(tmp_path: Path, monkeypatch):
    normalized, semantic = _ensure_dirs(tmp_path)
    db_path = semantic / "tags.db"
    monkeypatch.setattr(tag_onboarding, "is_beta_strict", lambda *_: True, raising=False)
    with pytest.raises(ConfigError):
        scan_normalized_to_db(normalized_dir=normalized, db_path=db_path, repo_root_dir=None)


def test_scan_normalized_non_strict_logs_fallback(monkeypatch, tmp_path: Path, caplog):
    normalized, semantic = _ensure_dirs(tmp_path)
    db_path = semantic / "tags.db"
    monkeypatch.setattr(tag_onboarding, "is_beta_strict", lambda *_: False, raising=False)
    caplog.set_level(logging.WARNING)
    stats = scan_normalized_to_db(normalized_dir=normalized, db_path=db_path, repo_root_dir=None)
    assert stats["folders"] == 0
    assert stats["documents"] == 0
    record = next(r for r in caplog.records if r.msg == "cli.tag_onboarding.repo_root_fallback")
    assert getattr(record, "service_only", None) is True


def test_run_nlp_strict_requires_repo_root(tmp_path: Path, monkeypatch):
    normalized, semantic = _ensure_dirs(tmp_path)
    db_path = semantic / "tags.db"
    monkeypatch.setattr(tag_onboarding.nlp_runner, "run_doc_terms_pipeline", lambda *_, **__: {}, raising=False)
    monkeypatch.setattr(tag_onboarding, "is_beta_strict", lambda *_: True, raising=False)
    with pytest.raises(ConfigError):
        run_nlp_to_db(slug="s", normalized_dir=normalized, db_path=db_path, repo_root_dir=None)


def test_run_nlp_non_strict_logs_fallback(monkeypatch, tmp_path: Path, caplog):
    normalized, semantic = _ensure_dirs(tmp_path)
    db_path = semantic / "tags.db"
    monkeypatch.setattr(tag_onboarding, "is_beta_strict", lambda *_: False, raising=False)
    monkeypatch.setattr(tag_onboarding.nlp_runner, "run_doc_terms_pipeline", lambda *_, **__: {}, raising=False)
    caplog.set_level(logging.WARNING)
    run_nlp_to_db(slug="s", normalized_dir=normalized, db_path=db_path, repo_root_dir=None)
    record = next(r for r in caplog.records if r.msg == "cli.tag_onboarding.repo_root_fallback")
    assert getattr(record, "service_only", None) is True
