# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

import ui.manage.tags as tags
from pipeline.exceptions import ConfigError
from ui.manage.tags import DEFAULT_TAGS_YAML


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
    content = (
        "version: 2\n"
        "keep_only_listed: true\n"
        "tags:\n"
        "  - name: demo\n"
        "    action: keep\n"
        "    synonyms:\n"
        "      - demo2\n"
        "    note: ''\n"
    )
    parsed = tags._validate_tags_yaml_payload(content)
    assert str(parsed["version"]) in {"2", "2.0"}
    assert parsed["keep_only_listed"] is True
    assert parsed["tags"][0]["synonyms"] == ["demo2"]


def test_validate_tags_yaml_payload_rejects_keep_only_listed_non_bool() -> None:
    content = 'version: 2\nkeep_only_listed: "yes"\ntags: []\n'
    with pytest.raises(ConfigError):
        tags._validate_tags_yaml_payload(content)


def test_validate_tags_yaml_payload_rejects_invalid_tag_entry() -> None:
    content = "version: 2\n" "keep_only_listed: false\n" "tags:\n" "  - name: ''\n"
    with pytest.raises(ConfigError):
        tags._validate_tags_yaml_payload(content)

    content_bad_synonyms = "version: 2\n" "keep_only_listed: false\n" "tags:\n" "  - name: demo\n" "    synonyms: bad\n"
    with pytest.raises(ConfigError):
        tags._validate_tags_yaml_payload(content_bad_synonyms)

    content_bad_action = "version: 2\n" "keep_only_listed: true\n" "tags:\n" "  - name: demo\n" "    action: UNKNOWN\n"
    with pytest.raises(ConfigError):
        tags._validate_tags_yaml_payload(content_bad_action)

    # note deve restare stringa
    content_bad_note = "version: 2\n" "keep_only_listed: true\n" "tags:\n" "  - name: demo\n" "    note: 3\n"
    with pytest.raises(ConfigError):
        tags._validate_tags_yaml_payload(content_bad_note)

    # fallback default
    content_defaults = "version: 2\n" "keep_only_listed: false\n" "tags:\n" "  - name: demo\n"
    parsed = tags._validate_tags_yaml_payload(content_defaults)
    assert parsed["tags"][0]["action"] == "keep"
    assert parsed["tags"][0]["note"] == ""


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


def test_enable_tags_stub_returns_false_when_state_update_fails(tmp_path: Path) -> None:
    st_stub = _StreamlitStub()
    semantic_dir = tmp_path / "semantic"
    yaml_path = semantic_dir / "tags_reviewed.yaml"

    ok = tags.enable_tags_stub(
        "demo",
        semantic_dir,
        yaml_path,
        st=st_stub,
        logger=logging.getLogger("test.manage.tags"),
        set_client_state=lambda _slug, _state: False,
        reset_gating_cache=lambda _slug: None,
        import_yaml_fn=lambda *args, **kwargs: {"terms": 1},
    )

    assert ok is False
    assert any("Aggiornamento stato cliente" in message for message in st_stub.errors)


def test_enable_tags_service_returns_false_when_state_update_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st_stub = _StreamlitStub()
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir()
    csv_path = tmp_path / "tags_raw.csv"
    csv_path.write_text("relative_path,suggested_tags,entities,keyphrases,score,sources\n", encoding="utf-8")
    yaml_path = semantic_dir / "tags_reviewed.yaml"
    db_path = semantic_dir / "tags.db"

    def fake_write_stub(_semantic_dir: Path, _csv: Path, _logger: Any) -> None:
        yaml_path.write_text(DEFAULT_TAGS_YAML, encoding="utf-8")

    def fake_export(_semantic_dir: Path, _db_path: Path, _logger: Any) -> None:
        pass

    monkeypatch.setattr("semantic.tags_io.write_tags_review_stub_from_csv", fake_write_stub)
    monkeypatch.setattr("semantic.api.export_tags_yaml_from_db", fake_export)
    monkeypatch.setattr("storage.tags_store.derive_db_path_from_yaml_path", lambda _path: str(db_path))

    ok = tags.enable_tags_service(
        "demo",
        semantic_dir,
        csv_path,
        yaml_path,
        st=st_stub,
        logger=logging.getLogger("test.manage.tags"),
        set_client_state=lambda _slug, _state: False,
        reset_gating_cache=lambda _slug: None,
    )

    assert ok is False
    assert any(
        "Abilitazione semantica riuscita ma aggiornamento stato fallito" in message for message in st_stub.errors
    )
