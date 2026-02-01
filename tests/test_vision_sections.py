# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from pipeline.exceptions import ConfigError
from semantic.vision_provision import _parse_required_sections


def test_missing_sections_raises():
    text = "Vision\nA\n\nMission\nB\n\nGoal\nC\n"
    with pytest.raises(ConfigError) as exc:
        _parse_required_sections(text)
    m = str(exc.value).lower()
    assert "sezioni mancanti" in m
    assert "framework etico" in m
    assert "contesto operativo" in m


def test_all_sections_ok():
    text = """Vision
A
Mission
B
Goal
C
Framework etico
D
Contesto Operativo
E
"""
    sections = _parse_required_sections(text)
    assert all(
        sections[k]
        for k in (
            "Vision",
            "Mission",
            "Goal",
            "Framework Etico",
            "Contesto Operativo",
        )
    )
