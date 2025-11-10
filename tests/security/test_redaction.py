# SPDX-License-Identifier: GPL-3.0-only
# tests/security/test_redaction.py
from __future__ import annotations

import pytest

from semantic.redaction import redact_sensitive_tokens


@pytest.mark.parametrize(
    ("text", "token", "placeholder"),
    [
        ("CF: RSSMRA85T10A562S", "RSSMRA85T10A562S", "[[REDACTED:CF]]"),
        (
            "IBAN IT60X0542811101000000123456",
            "IT60X0542811101000000123456",
            "[[REDACTED:IBAN]]",
        ),  # pragma: allowlist secret
        ("Scrivi a persona@example.com", "persona@example.com", "[[REDACTED:EMAIL]]"),
        ("Tel. +39 347 123 4567", "+39 347 123 4567", "[[REDACTED:PHONE]]"),
    ],
)
def test_redaction_masks_sensitive_tokens(text: str, token: str, placeholder: str) -> None:
    redacted = redact_sensitive_tokens(text)
    assert placeholder in redacted
    assert token not in redacted


def test_redaction_handles_generic_tax_id() -> None:
    dummy_tax_id = "AB12CD34EF56"  # pragma: allowlist secret
    redacted = redact_sensitive_tokens(f"Identificativo: {dummy_tax_id}")
    assert "[[REDACTED:TAXID]]" in redacted
    assert dummy_tax_id not in redacted


def test_redaction_no_sensitive_data_returns_input() -> None:
    text = "Documento privo di dati sensibili."
    assert redact_sensitive_tokens(text) == text


def test_redaction_masks_multiple_tokens() -> None:
    text = "Contatta persona@example.com o chiama +39 02 1234 5678."
    redacted = redact_sensitive_tokens(text)
    assert redacted.count("[[REDACTED:EMAIL]]") == 1
    assert redacted.count("[[REDACTED:PHONE]]") == 1
    assert "persona@example.com" not in redacted
    assert "+39 02 1234 5678" not in redacted
