# SPDX-License-Identifier: GPL-3.0-only
# tests/ui/test_query_params_slug.py
from ui.utils.query_params import get_slug, set_slug


def test_get_slug_rejects_invalid():
    params = {"slug": "../../etc"}
    assert get_slug(params) is None


def test_set_slug_normalizes_and_keeps_valid():
    params = {}
    set_slug(params, "  Cliente-ABC  ")
    assert params["slug"] == "cliente-abc"
