# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline.exceptions import InvalidSlug
from pipeline.path_utils import to_kebab_strict


@pytest.mark.parametrize(
    "candidate",
    [
        "",
        "   ",
        "@@@@$",
        "!!!---",
        "\n",
    ],
)
def test_to_kebab_strict_rejects_empty_or_placeholder(candidate: str) -> None:
    with pytest.raises(InvalidSlug):
        to_kebab_strict(candidate, context="tests.test_path_utils_kebab_strict")


def test_to_kebab_strict_accepts_valid_kebab() -> None:
    result = to_kebab_strict("Analisi Dati_AI", context="tests.test_path_utils_kebab_strict")
    assert result == "analisi-dati-ai"
