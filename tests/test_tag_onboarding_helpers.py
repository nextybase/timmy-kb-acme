# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.ingest import provider as ingest_provider
from timmy_kb.cli import tag_onboarding
from timmy_kb.cli import tag_onboarding_raw as raw_ingest
from timmy_kb.cli.tag_onboarding import _should_proceed  # type: ignore
from timmy_kb.cli.tag_onboarding import NlpRunOptions, run_nlp_to_db, scan_normalized_to_db
from timmy_kb.cli.tag_onboarding_raw import copy_from_local, download_from_drive


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _CaptureLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def info(self, event: str, extra=None, **_kwargs):  # noqa: ANN001
        self.events.append((event, dict(extra or {})))

    def warning(self, event: str, extra=None, **_kwargs):  # noqa: ANN001
        self.events.append((event, dict(extra or {})))

    def error(self, event: str, extra=None, **_kwargs):  # noqa: ANN001
        self.events.append((event, dict(extra or {})))


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


def test_repo_root_none_always_raises_config_error(monkeypatch, tmp_path: Path):
    normalized, semantic = _ensure_dirs(tmp_path)
    db_path = semantic / "tags.db"
    monkeypatch.setattr(tag_onboarding, "is_beta_strict", lambda *_: False, raising=False)
    monkeypatch.setattr(tag_onboarding.nlp_runner, "run_doc_terms_pipeline", lambda *_, **__: {}, raising=False)
    with pytest.raises(ConfigError):
        scan_normalized_to_db(normalized_dir=normalized, db_path=db_path, repo_root_dir=None)
    with pytest.raises(ConfigError):
        run_nlp_to_db(
            slug="s",
            normalized_dir=normalized,
            raw_dir=normalized,
            db_path=db_path,
            repo_root_dir=None,
            options=NlpRunOptions(enable_entities=False),
        )


def test_run_nlp_to_db_rejects_legacy_kwargs(monkeypatch, tmp_path: Path) -> None:
    normalized, semantic = _ensure_dirs(tmp_path)
    raw_dir = tmp_path / "workspace" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    db_path = semantic / "tags.db"
    with pytest.raises(TypeError):
        run_nlp_to_db(
            slug="s",
            normalized_dir=normalized,
            raw_dir=raw_dir,
            db_path=db_path,
            repo_root_dir=tmp_path / "workspace",
            options=NlpRunOptions(enable_entities=False),
            rebuild=True,
        )


def test_run_nlp_to_db_options_only_applies_values(monkeypatch, tmp_path: Path) -> None:
    normalized, semantic = _ensure_dirs(tmp_path)
    raw_dir = tmp_path / "workspace" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    db_path = semantic / "tags.db"

    captured: dict[str, object] = {}

    def _fake_pipeline(_conn, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return {"doc_terms": 0, "terms": 0, "folders": 0}

    log = _CaptureLogger()
    monkeypatch.setattr(tag_onboarding, "get_structured_logger", lambda *_a, **_k: log, raising=True)
    monkeypatch.setattr(tag_onboarding.nlp_runner, "run_doc_terms_pipeline", _fake_pipeline, raising=True)

    run_nlp_to_db(
        slug="s",
        normalized_dir=normalized,
        raw_dir=raw_dir,
        db_path=db_path,
        repo_root_dir=tmp_path / "workspace",
        options=NlpRunOptions(
            rebuild=True,
            only_missing=True,
            enable_entities=False,
            max_workers=2,
            worker_batch_size=5,
        ),
    )

    assert captured["rebuild"] is True
    assert captured["only_missing"] is True
    assert captured["worker_count"] == 2
    assert captured["worker_batch_size"] == 5
