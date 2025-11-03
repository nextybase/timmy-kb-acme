# SPDX-License-Identifier: GPL-3.0-only
# tests/ui/test_slug_sanitize.py
from ui.utils.slug import _sanitize_slug


def test_reject_invalid_slug():
    assert _sanitize_slug("../../etc") is None


def test_accept_valid_slug():
    assert _sanitize_slug("cliente-xyz") == "cliente-xyz"
