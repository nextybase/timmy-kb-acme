# SPDX-License-Identifier: GPL-3.0-only
# tests/security/test_masking.py
from __future__ import annotations

from pathlib import Path

from timmykb.security.masking import hash_identifier, mask_paths, sha256_path


def test_hash_identifier_deterministic() -> None:
    value = "Cliente DUMMY SPA"
    first = hash_identifier(value)
    second = hash_identifier(value)
    assert first == second
    assert len(first) == 12
    assert first != hash_identifier("cliente dummy spa")  # case-sensitive


def test_sha256_path_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "foo" / "bar.txt"
    value = sha256_path(path)
    assert value == sha256_path(path)
    assert len(value) == 12


def test_mask_paths_returns_mapping(tmp_path: Path) -> None:
    a = tmp_path / "mapping.yaml"
    b = tmp_path / "cartelle_raw.yaml"
    result = mask_paths(a, b)
    assert set(result.keys()) == {"mapping.yaml", "cartelle_raw.yaml"}
    assert result["mapping.yaml"] == sha256_path(a)
    assert result["cartelle_raw.yaml"] == sha256_path(b)
