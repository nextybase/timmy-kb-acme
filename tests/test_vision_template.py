# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import vision_template as vt
from pipeline.exceptions import ConfigError


def _set_template_path(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(vt, "vision_template_path", lambda: path)


def test_load_vision_template_missing_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    template_path = tmp_path / "vision_template.yaml"
    _set_template_path(monkeypatch, template_path)

    with pytest.raises(ConfigError, match=r"Vision template missing or invalid: config/vision_template.yaml"):
        vt.load_vision_template_sections()


def test_load_vision_template_invalid_yaml_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    template_path = tmp_path / "vision_template.yaml"
    template_path.write_text("sections: [", encoding="utf-8")
    _set_template_path(monkeypatch, template_path)

    with pytest.raises(ConfigError, match=r"Vision template missing or invalid: config/vision_template.yaml"):
        vt.load_vision_template_sections()


def test_load_vision_template_valid_returns_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    template_path = tmp_path / "vision_template.yaml"
    template_path.write_text("sections:\n  - {name: a}\n  - 123\n", encoding="utf-8")
    _set_template_path(monkeypatch, template_path)

    sections = vt.load_vision_template_sections()
    assert isinstance(sections, list)
    assert sections == [{"name": "a"}]
