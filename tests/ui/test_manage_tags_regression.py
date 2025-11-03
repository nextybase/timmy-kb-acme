# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest


class _StreamlitStub:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.toasts: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def toast(self, message: str) -> None:
        self.toasts.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


@pytest.fixture()
def manage_module(monkeypatch: pytest.MonkeyPatch) -> tuple[object, _StreamlitStub]:
    import ui.pages.manage as manage  # type: ignore

    stub = _StreamlitStub()
    monkeypatch.setattr(manage, "st", stub, raising=True)
    return manage, stub


def test_handle_tags_raw_save_normalizes_header_tokens(
    manage_module: tuple[object, _StreamlitStub],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manage, st_stub = manage_module
    semantic_dir = tmp_path / "semantic"
    csv_path = semantic_dir / "tags_raw.csv"

    written: dict[str, Path] = {}

    def _fake_write(path: Path, content: str, **_kw: object) -> None:
        written["path"] = path
        written["content"] = content

    monkeypatch.setattr(manage, "safe_write_text", _fake_write, raising=True)
    caplog.set_level("WARNING")

    content = "Name , SUGGESTED_TAGS , Other\nrow1\n"
    ok = manage._handle_tags_raw_save("dummy", content, csv_path, semantic_dir)

    assert ok is True
    assert not st_stub.errors
    assert written["path"] == csv_path
    assert "row1" in written["content"]
    assert not any(record.message == "ui.manage.tags_raw.invalid_header" for record in caplog.records)


def test_handle_tags_raw_enable_logs_when_service_missing(
    manage_module: tuple[object, _StreamlitStub],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manage, st_stub = manage_module
    monkeypatch.setattr(manage, "_run_tags_update", None, raising=True)
    monkeypatch.delenv("TAGS_MODE", raising=False)
    monkeypatch.setattr(manage, "_enable_tags_stub", lambda *a, **k: False, raising=True)
    monkeypatch.setattr(manage, "_enable_tags_service", lambda *a, **k: False, raising=True)

    caplog.set_level("ERROR")

    semantic_dir = tmp_path / "semantic"
    csv_path = tmp_path / "tags_raw.csv"
    yaml_path = tmp_path / "tags_reviewed.yaml"

    ok = manage._handle_tags_raw_enable("dummy", semantic_dir, csv_path, yaml_path)

    assert ok is False
    assert st_stub.errors  # segnalazione utente
    records = [rec for rec in caplog.records if rec.message == "ui.manage.tags.service_missing"]
    assert records, "Log ui.manage.tags.service_missing assente"
    record = records[0]
    assert getattr(record, "slug", None) == "dummy"
    assert getattr(record, "mode", None) == "default"
