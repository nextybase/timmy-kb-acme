from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError
from semantic.validation import validate_context_slug


def test_validate_context_slug_happy_path() -> None:
    data = {"context": {"slug": "acme", "client_name": "Acme"}}
    # Non deve sollevare
    validate_context_slug(data, expected_slug="acme")


@pytest.mark.parametrize(
    "payload, expected_exc",
    [
        ({"context": 123}, ConfigError),
        ({"context": {"slug": ""}}, ConfigError),
        ({"context": {"slug": "other"}}, ConfigError),
    ],
)
def test_validate_context_slug_negatives(payload, expected_exc) -> None:
    with pytest.raises(expected_exc):
        validate_context_slug(payload, expected_slug="acme")
