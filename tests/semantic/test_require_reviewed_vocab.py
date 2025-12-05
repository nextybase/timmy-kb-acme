# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from semantic import api


def _make_loader(
    result: dict[str, dict[str, list[str]]],
    *,
    module_name: str = "semantic.vocab_loader",
) -> callable[[Path, logging.Logger], dict[str, dict[str, list[str]]]]:
    def _loader(_: Path, __: logging.Logger) -> dict[str, dict[str, list[str]]]:
        return result

    _loader.__module__ = module_name
    return _loader


def test_require_reviewed_vocab_returns_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "dummy"
    (base_dir / "semantic").mkdir(parents=True)
    logger = logging.getLogger("test.semantic.require")
    expected = {"areas": {"area": ["term"]}}
    monkeypatch.setattr(api, "_load_reviewed_vocab", _make_loader(expected))

    vocab = api.require_reviewed_vocab(base_dir, logger, slug="dummy")

    assert vocab == expected


def test_require_reviewed_vocab_detects_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "dummy"
    (base_dir / "semantic").mkdir(parents=True)
    logger = logging.getLogger("test.semantic.require.stub")
    monkeypatch.setattr(api, "_load_reviewed_vocab", _make_loader({}, module_name="tests.stub"))

    with pytest.raises(ConfigError) as excinfo:
        api.require_reviewed_vocab(base_dir, logger, slug="dummy")

    text = str(excinfo.value)
    assert "Vocabolario canonico assente" in text
    assert excinfo.value.file_path == base_dir / "semantic" / "tags.db"


def test_require_reviewed_vocab_requires_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "dummy"
    (base_dir / "semantic").mkdir(parents=True)
    logger = logging.getLogger("test.semantic.require.empty")
    monkeypatch.setattr(api, "_load_reviewed_vocab", _make_loader({}))

    with pytest.raises(ConfigError) as excinfo:
        api.require_reviewed_vocab(base_dir, logger, slug="dummy")

    assert "Vocabolario canonico assente" in str(excinfo.value)
    assert excinfo.value.file_path == base_dir / "semantic" / "tags.db"
