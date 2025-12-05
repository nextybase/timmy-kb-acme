# SPDX-License-Identifier: GPL-3.0-or-later
from types import MappingProxyType

from ui.utils.merge import deep_merge_dict


def test_contract_accepts_mapping_inputs_and_returns_dict() -> None:
    base = MappingProxyType({"a": {"b": 1}, "c": 2})
    override = MappingProxyType({"a": {"d": 3}})

    merged = deep_merge_dict(base, override)

    assert isinstance(merged, dict)
    assert merged["a"] == {"b": 1, "d": 3}
    assert merged["c"] == 2


def test_contract_does_not_mutate_inputs() -> None:
    base = {"alpha": {"x": 1}, "beta": 2}
    override = {"alpha": {"y": 9}}

    merged = deep_merge_dict(base, override)

    assert base == {"alpha": {"x": 1}, "beta": 2}
    assert override == {"alpha": {"y": 9}}
    assert merged["alpha"] == {"x": 1, "y": 9}
    assert merged["beta"] == 2


def test_contract_preserves_value_types_on_partial_override() -> None:
    base = {"k": {"a": 1, "b": 2.0}}
    override = {"k": {"b": 3}}

    merged = deep_merge_dict(base, override)

    assert isinstance(merged["k"]["a"], int)
    assert merged["k"]["a"] == 1
    assert isinstance(merged["k"]["b"], int)
    assert merged["k"]["b"] == 3
