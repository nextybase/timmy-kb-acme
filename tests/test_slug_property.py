from __future__ import annotations

import re

import pytest

hypothesis = pytest.importorskip("hypothesis")
strategies = pytest.importorskip("hypothesis.strategies")
given = hypothesis.given
st = strategies
import pytest

from pipeline.path_utils import to_kebab

_ALLOWED_RE = re.compile(r"^[a-z0-9-]*$")


@given(st.text())
def test_to_kebab_produces_allowed_charset(input_text: str) -> None:
    result = to_kebab(input_text)
    assert _ALLOWED_RE.fullmatch(result) is not None


@given(st.text())
def test_to_kebab_has_no_duplicate_or_border_hyphen(input_text: str) -> None:
    result = to_kebab(input_text)
    assert "--" not in result
    if result:
        assert not result.startswith("-"), "kebab output should not start with hyphen"
        assert not result.endswith("-"), "kebab output should not end with hyphen"


@given(st.text())
def test_to_kebab_idempotent(input_text: str) -> None:
    result = to_kebab(input_text)
    assert to_kebab(result) == result


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Hello World", "hello-world"),
        ("multi__separator--test", "multi-separator-test"),
        ("   SPACES   ", "spaces"),
        ("\u00e0\u00e8\u00ec\u00f2\u00f9", ""),
        ("Already-Kebab", "already-kebab"),
    ],
)
def test_to_kebab_examples(raw: str, expected: str) -> None:
    assert to_kebab(raw) == expected
