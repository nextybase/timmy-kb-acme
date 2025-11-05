# SPDX-License-Identifier: GPL-3.0-only
# tests/test_windows_path_utils.py

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline.file_utils import safe_append_text, safe_write_text
from pipeline.path_utils import strip_extended_length_path, to_extended_length_path


def _build_long_path(base: Path, *, depth: int = 8, segment_len: int = 20) -> Path:
    """
    Crea un percorso annidato con nome totale > 260 caratteri (Windows MAX_PATH).
    """
    current = base
    for idx in range(depth):
        current /= f"segment_{idx:02d}_{'x' * segment_len}"
    current.mkdir(parents=True, exist_ok=True)
    return current / ("payload_" + "y" * segment_len + ".txt")


def test_to_extended_length_path_posix_noop(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Il comportamento POSIX viene verificato solo su sistemi non Windows.")
    example = tmp_path / "example.txt"
    extended = to_extended_length_path(example)
    assert extended == str(example)
    restored = strip_extended_length_path(extended)
    assert restored == example


@pytest.mark.skipif(os.name != "nt", reason="Richiede Windows per testare i prefissi estesi.")
def test_to_extended_length_path_windows_roundtrip(tmp_path: Path) -> None:
    target = _build_long_path(tmp_path)
    extended = to_extended_length_path(target)
    assert extended.startswith("\\\\?\\")
    restored = strip_extended_length_path(extended)
    assert os.path.normcase(str(restored)) == os.path.normcase(str(target))


@pytest.mark.skipif(os.name != "nt", reason="Richiede Windows per testare i prefissi estesi.")
def test_safe_write_text_handles_long_paths(tmp_path: Path) -> None:
    target = _build_long_path(tmp_path)
    safe_write_text(target, "contenuto", atomic=True)
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "contenuto"


@pytest.mark.skipif(os.name != "nt", reason="Richiede Windows per testare i prefissi estesi.")
def test_safe_append_text_on_long_paths(tmp_path: Path) -> None:
    base = tmp_path / "workspace"
    base.mkdir(parents=True, exist_ok=True)

    target = _build_long_path(base, depth=5, segment_len=24)
    rel_target = target.relative_to(base)

    safe_append_text(base, rel_target, "riga-1\n", fsync=True)
    safe_append_text(base, rel_target, "riga-2\n", fsync=False)

    contents = target.read_text(encoding="utf-8")
    assert contents == "riga-1\nriga-2\n"
