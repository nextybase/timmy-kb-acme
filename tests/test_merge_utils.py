# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from ui.utils.merge import deep_merge_dict

pytestmark = pytest.mark.unit


def test_deep_merge_preserves_nested() -> None:
    base = {"vision": {"schema": 1, "fields": {"a": 1, "b": 2}}, "other": 1}
    override = {"vision": {"fields": {"b": 99, "c": 3}}}

    merged = deep_merge_dict(base, override)

    assert merged["vision"]["schema"] == 1
    assert merged["vision"]["fields"] == {"a": 1, "b": 99, "c": 3}
    assert merged["other"] == 1


def test_deep_merge_override_scalar() -> None:
    base = {"foo": {"bar": 1}, "other": 1}
    override = {"foo": 2}

    merged = deep_merge_dict(base, override)

    assert merged["foo"] == 2
    assert merged["other"] == 1
