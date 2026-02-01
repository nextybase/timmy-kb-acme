# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

import pytest

from security import masking


def test_hash_identifier_uses_32_chars() -> None:
    digest = masking.hash_identifier("customer-acme")
    assert len(digest) == 32
    assert digest == masking.hash_identifier("customer-acme")


def test_hash_identifier_respects_salt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(os.environ, "TIMMY_HASH_SALT", "pepper")
    salted = masking.hash_identifier("customer-x")
    monkeypatch.setitem(os.environ, "TIMMY_HASH_SALT", "paprika")
    salted_2 = masking.hash_identifier("customer-x")
    assert salted != salted_2


def test_mask_paths_uses_extended_hash(tmp_path: Path) -> None:
    file_path = tmp_path / "demo.txt"
    file_path.write_text("demo", encoding="utf-8")
    masked = masking.mask_paths(file_path)
    digest = masked["demo.txt"]
    assert len(digest) == 32
