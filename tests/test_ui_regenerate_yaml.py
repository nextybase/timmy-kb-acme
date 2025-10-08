# tests/test_ui_regenerate_yaml.py
from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError
from semantic.validation import validate_context_slug


def test_mapping_yaml_requires_expected_slug():
    """Il mapping deve avere context.slug coerente con lo slug atteso."""
    mapping_ok = {"context": {"slug": "acme"}}
    validate_context_slug(mapping_ok, expected_slug="acme")

    mapping_bad = {"context": {"slug": "wrong"}}
    with pytest.raises(ConfigError):
        validate_context_slug(mapping_bad, expected_slug="acme")


def test_cartelle_yaml_needs_context_slug_and_becomes_valid_after_fix():
    """
    In Beta 0 la UI fa 'auto-heal' sullo slug mancante nelle cartelle.
    Il test verifica che:
      - senza context.slug fallisce
      - aggiungendo context.slug diventa valido
    """
    cartelle = {"version": 1, "folders": []}  # manca context.slug
    with pytest.raises(ConfigError):
        validate_context_slug(cartelle, expected_slug="acme")

    # Emuliamo l'auto-heal della UI (aggiunta context.slug coerente)
    cartelle["context"] = {"slug": "acme"}
    validate_context_slug(cartelle, expected_slug="acme")
