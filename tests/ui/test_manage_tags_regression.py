# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import ui.manage.tags as tags
from pipeline.exceptions import ConfigError


class _StreamlitStub:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.toasts: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def info(self, message: str) -> None:
        self.warnings.append(message)

    def toast(self, message: str) -> None:
        self.toasts.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


def test_handle_tags_raw_save_normalizes_header_tokens(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    st_stub = _StreamlitStub()
    logger = logging.getLogger("test.manage.tags.save")
    logger.propagate = True
    caplog.set_level("WARNING", logger=logger.name)

    semantic_dir = tmp_path / "semantic"
    csv_path = semantic_dir / "tags_raw.csv"

    written: dict[str, Path] = {}

    def _fake_write(path: Path, content: str, **_kw: object) -> None:
        written["path"] = path
        written["content"] = content

    monkeypatch.setattr(tags, "safe_write_text", _fake_write, raising=True)

    content = "Name , SUGGESTED_TAGS , Other\nrow1\n"
    ok = tags.handle_tags_raw_save(
        "dummy",
        content,
        csv_path,
        semantic_dir,
        st=st_stub,
        logger=logger,
    )

    assert ok is True
    assert not st_stub.errors
    assert written["path"] == csv_path
    assert "row1" in written["content"]
    assert not any(record.message == "ui.manage.tags_raw.invalid_header" for record in caplog.records)


def test_handle_tags_raw_enable_logs_when_service_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    st_stub = _StreamlitStub()
    logger = logging.getLogger("test.manage.tags.enable")
    logger.propagate = True
    caplog.set_level("ERROR", logger=logger.name)

    semantic_dir = tmp_path / "semantic"
    csv_path = tmp_path / "tags_raw.csv"
    yaml_path = tmp_path / "tags_reviewed.yaml"

    ok = tags.handle_tags_raw_enable(
        "dummy",
        semantic_dir,
        csv_path,
        yaml_path,
        st=st_stub,
        logger=logger,
        tags_mode="default",
        run_tags_fn=None,
        set_client_state=lambda _slug, _state: False,
        reset_gating_cache=lambda _slug: None,
    )

    assert ok is False
    assert st_stub.errors  # segnalazione utente
    records = [rec for rec in caplog.records if rec.message == "ui.manage.tags.service_missing"]
    assert records, "Log ui.manage.tags.service_missing assente"
    record = records[0]
    assert getattr(record, "slug", None) == "dummy"
    assert getattr(record, "mode", None) == "default"


def test_validate_tags_yaml_payload_requires_version() -> None:
    content = "keep_only_listed: true\ntags: []\n"
    with pytest.raises(ConfigError):
        tags._validate_tags_yaml_payload(content)


def test_validate_tags_yaml_payload_accepts_schema() -> None:
    content = "version: 2\nkeep_only_listed: true\ntags:\n  - name: demo\n"
    parsed = tags._validate_tags_yaml_payload(content)
    assert parsed["version"] == 2
    assert parsed["keep_only_listed"] is True


def test_enable_tags_service_fails_when_csv_missing(tmp_path: Path) -> None:
    st_stub = _StreamlitStub()
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir()
    yaml_path = semantic_dir / "tags_reviewed.yaml"

    ok = tags.enable_tags_service(
        "demo",
        semantic_dir,
        tmp_path / "missing.csv",
        yaml_path,
        st=st_stub,
        logger=logging.getLogger("test.manage.tags"),
        set_client_state=lambda _slug, _state: True,
        reset_gating_cache=lambda _slug: None,
    )

    assert ok is False
    assert st_stub.errors  # messaggio utente presente
