# src/semantic/redaction.py
from __future__ import annotations

import re
from typing import Tuple

__all__ = ["redact_sensitive_tokens"]

_REPLACEMENT_TEMPLATE = "[[REDACTED:{type}]]"

_CF_PATTERN = re.compile(
    r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b",
    flags=re.IGNORECASE,
)

_IBAN_PATTERN = re.compile(
    r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b",
    flags=re.IGNORECASE,
)

_EMAIL_PATTERN = re.compile(
    r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b",
    flags=re.IGNORECASE,
)

_PHONE_PATTERN = re.compile(
    r"""
    (?<!\w)               # vincolo sinistro per evitare parole adiacenti
    (?=(?:.*\d){7,})      # almeno 7 cifre complessive
    (?:\+?\d{1,3}[\s\-.]?)?
    (?:\(?\d{2,4}\)?[\s\-.]?){1,4}
    \d{2,6}
    (?!\w)                # vincolo destro
    """,
    flags=re.VERBOSE,
)

_GENERIC_TAX_ID_PATTERN = re.compile(
    r"""
    \b
    (?=[A-Z0-9]{10,16}\b)           # lunghezza 10-16
    (?=.*[A-Z])(?=.*\d)             # almeno una lettera e una cifra
    [A-Z0-9]+
    \b
    """,
    flags=re.VERBOSE | re.IGNORECASE,
)

_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (_CF_PATTERN, "CF"),
    (_IBAN_PATTERN, "IBAN"),
    (_EMAIL_PATTERN, "EMAIL"),
    (_PHONE_PATTERN, "PHONE"),
    (_GENERIC_TAX_ID_PATTERN, "TAXID"),
)


def redact_sensitive_tokens(text: str) -> str:
    """Maschera token sensibili restituendo il testo redatto."""
    redacted = text
    for pattern, token_type in _PATTERNS:
        placeholder = _REPLACEMENT_TEMPLATE.format(type=token_type)
        redacted = pattern.sub(placeholder, redacted)
    return redacted
