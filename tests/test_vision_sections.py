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
    assert "descrizione prodotto/azienda" in m
    assert "descrizione mercato" in m


def test_all_sections_ok():
    text = """Vision
A
Mission
B
Goal
C
Framework etico
D
Descrizione prodotto/azienda
E
Descrizione mercato
F
"""
    sections = _parse_required_sections(text)
    assert all(
        sections[k]
        for k in (
            "Vision",
            "Mission",
            "Goal",
            "Framework etico",
            "Descrizione prodotto/azienda",
            "Descrizione mercato",
        )
    )
