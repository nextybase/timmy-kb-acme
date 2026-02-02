# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from tools.vision import vision_parser as vp


def test_split_sections_no_headers_raises() -> None:
    text = "Testo senza header validi."
    expected = "Vision sections missing or empty: " + ", ".join(vp.REQUIRED_VISION_SECTIONS)
    with pytest.raises(ConfigError, match=re.escape(expected)):
        vp._split_sections(text)


def test_split_sections_required_empty_raises() -> None:
    text = (
        "Vision\n"
        "\n"
        "Mission\n"
        "Test mission.\n"
        "Framework etico\n"
        "Test framework.\n"
        "Goal\n"
        "- Goal 1 - Test goal.\n"
        "Descrizione prodotto\n"
        "Test prodotto.\n"
        "Descrizione mercato\n"
        "Test mercato.\n"
    )
    expected = "Vision sections missing or empty: vision"
    with pytest.raises(ConfigError, match=re.escape(expected)):
        vp._split_sections(text)


def test_goal_blocks_missing_raises() -> None:
    with pytest.raises(ConfigError, match=r"Goal format invalid: expected 'Goal N' blocks"):
        vp._split_goal_baskets("Obiettivi senza numerazione")


def test_happy_path_sections_and_goals() -> None:
    text = (
        "Vision\n"
        "Test vision.\n"
        "Mission\n"
        "Test mission.\n"
        "Framework etico\n"
        "Test framework.\n"
        "Goal\n"
        "- Goal 1 - Test goal.\n"
        "Descrizione prodotto\n"
        "Test prodotto.\n"
        "Descrizione mercato\n"
        "Test mercato.\n"
    )
    sections = vp._split_sections(text)
    goals = vp._split_goal_baskets(sections["goal"])
    assert goals["b3"] == ["Test goal."]


def test_read_pdf_text_failure_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%dummy\n")

    def _boom(_path: Path) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(vp, "read_document", _boom, raising=True)

    with pytest.raises(ConfigError, match=r"Impossibile leggere il PDF\.") as excinfo:
        vp._read_pdf_text(pdf_path)

    err = excinfo.value
    assert getattr(err, "file_path", None) == str(pdf_path)
    assert "boom" not in str(err)
