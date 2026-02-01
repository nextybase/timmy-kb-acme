# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError
from semantic.vision_provision import REQUIRED_SECTIONS_CANONICAL, _parse_required_sections


def _mk_text(contesto_heading: str) -> str:
    return (
        "Vision\n"
        "Test vision...\n"
        "Mission\n"
        "Test mission...\n"
        "Goal\n"
        "Test goal...\n"
        "Framework etico\n"
        "Test framework...\n"
        f"{contesto_heading}\n"
        "Test contesto...\n"
    )


@pytest.mark.parametrize(
    "heading",
    [
        "Contesto Operativo",
        "Contesto operativo",
        "Contesto Operativo:",
        "Contesto operativo:",
    ],
)
def test_header_variants_are_canonical(heading: str):
    text = _mk_text(heading)
    sections = _parse_required_sections(text)
    for canon in REQUIRED_SECTIONS_CANONICAL:
        assert canon in sections, f"Sezione canonica mancante: {canon}"
        assert isinstance(sections[canon], str) and sections[canon].strip(), f"Sezione vuota: {canon}"


def test_missing_sections_raise_configerror():
    text = _mk_text("Contesto Operativo").replace("Contesto Operativo\nTest contesto...\n", "")
    with pytest.raises(ConfigError) as exc:
        _parse_required_sections(text)
    msg = str(exc.value)
    assert "Contesto Operativo" in msg or "mancanti" in msg
