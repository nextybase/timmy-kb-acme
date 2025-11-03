# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError
from semantic.vision_provision import REQUIRED_SECTIONS_CANONICAL, _parse_required_sections


def _mk_text(prod_heading: str, market_heading: str) -> str:
    return (
        "Vision\n"
        "Test vision...\n"
        "Mission\n"
        "Test mission...\n"
        "Goal\n"
        "Test goal...\n"
        "Framework etico\n"
        "Test framework...\n"
        f"{prod_heading}\n"
        "Test prodotto/azienda...\n"
        f"{market_heading}\n"
        "Test mercato...\n"
    )


@pytest.mark.parametrize(
    "prod, market",
    [
        ("Prodotto/Azienda", "Mercato"),
        ("Prodotto / Azienda", "Mercato"),
        ("Descrizione prodotto/azienda", "Descrizione mercato"),
        ("Descrizione prodotto/azienda:", "Descrizione mercato:"),
        ("Prodotto/Azienda:", "Mercato:"),
    ],
)
def test_header_variants_are_canonical(prod: str, market: str):
    text = _mk_text(prod, market)
    sections = _parse_required_sections(text)
    # Devono esserci TUTTI i canonici
    for canon in REQUIRED_SECTIONS_CANONICAL:
        assert canon in sections, f"Sezione canonica mancante: {canon}"
        assert isinstance(sections[canon], str) and sections[canon].strip(), f"Sezione vuota: {canon}"
    # Le due sezioni chiave devono essere quelle canoniche
    assert "Prodotto/Azienda" in sections
    assert "Mercato" in sections


def test_missing_sections_raise_configerror():
    # Rimuoviamo volutamente la sezione Mercato
    text = _mk_text("Prodotto/Azienda", "Mercato").replace("Mercato\nTest mercato...\n", "")
    with pytest.raises(ConfigError) as exc:
        _parse_required_sections(text)
    msg = str(exc.value)
    assert "Mercato" in msg or "mancanti" in msg
