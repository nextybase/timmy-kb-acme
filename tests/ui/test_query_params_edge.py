# SPDX-License-Identifier: GPL-3.0-only
# tests/ui/test_query_params_edge.py
from __future__ import annotations

from typing import Any, MutableMapping

from ui.utils.query_params import get_slug, set_slug


def test_get_slug_with_list_and_whitespace_and_validation_ok():
    params: MutableMapping[str, Any] = {"slug": ["  dummy-01  ", "bad"]}
    # "dummy-01" deve essere normalizzato e validato → accettato
    assert get_slug(params) == "dummy-01"


def test_get_slug_non_string_returns_none():
    params: MutableMapping[str, Any] = {"slug": 12345}
    assert get_slug(params) is None


def test_get_slug_whitespace_only_returns_none():
    params: MutableMapping[str, Any] = {"slug": "   "}
    assert get_slug(params) is None


def test_set_slug_invalid_does_not_write_param():
    params: MutableMapping[str, Any] = {}
    # slug invalido (contiene path traversal / caratteri proibiti)
    set_slug(params, "../../etc")
    assert "slug" not in params


def test_set_slug_valid_writes_normalized():
    params: MutableMapping[str, Any] = {}
    set_slug(params, "  dummy-02  ")
    assert params.get("slug") == "dummy-02"
