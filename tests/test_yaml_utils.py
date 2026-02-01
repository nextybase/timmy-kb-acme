# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.yaml_utils import clear_yaml_cache, yaml_read

pytestmark = pytest.mark.unit


def test_yaml_read_ok(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    p = base / "cfg.yaml"
    p.write_text("a: 1\nb: test\n", encoding="utf-8")

    clear_yaml_cache()
    data = yaml_read(base, p)
    assert isinstance(data, dict)
    assert data["a"] == 1 and data["b"] == "test"


def test_yaml_read_blocks_traversal(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("x: 1\n", encoding="utf-8")

    clear_yaml_cache()
    with pytest.raises(ConfigError):
        # Percorso fuori da base
        yaml_read(base, outside)


def test_yaml_cache_invalidates_on_size_mtime_change(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    p = base / "conf.yaml"

    # Scrive valore iniziale
    p.write_text("value: 1\n", encoding="utf-8")
    clear_yaml_cache()
    d1 = yaml_read(base, p)
    assert d1.get("value") == 1

    # Aggiorna contenuto con dimensione diversa (invalida cache via size/mtime)
    p.write_text("value: 1234567\n", encoding="utf-8")
    # Ritocca anche mtime per evitare edge su FS esotici (best-effort)
    try:
        st = p.stat()
        os.utime(p, (st.st_atime, st.st_mtime + 2))
    except Exception:
        pass

    d2 = yaml_read(base, p)
    assert d2.get("value") == 1234567


def test_yaml_malformed_raises_configerror(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    bad = base / "bad.yaml"
    bad.write_text("a: [1, 2\n", encoding="utf-8")  # parentesi non chiusa

    clear_yaml_cache()
    with pytest.raises(ConfigError):
        yaml_read(base, bad)
