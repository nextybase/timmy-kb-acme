# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def warning(self, *args, **kwargs):
        pass


class _Ctx:
    def __init__(self, base_dir: Path):
        self.base_dir = str(base_dir)


def _make_symlink(src: Path, dst: Path) -> None:
    try:
        dst.symlink_to(src)
    except OSError as e:  # pragma: no cover - piattaforme senza permessi symlink
        pytest.skip(f"symlink not supported on this platform: {e}")


def test_pdf_path_outside_base_dir_is_rejected_with_slug_and_file(tmp_path: Path):
    base = tmp_path / "kb"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    outside_pdf = tmp_path / "outside.pdf"
    outside_pdf.write_bytes(b"%PDF-1.4\n%\n")

    from semantic.vision_provision import provision_from_vision as prov

    ctx = _Ctx(base)
    with pytest.raises(ConfigError) as ei:
        prov(ctx, _NoopLogger(), slug="dummy", pdf_path=outside_pdf)
    err = ei.value
    # Deve includere slug e file_path
    assert getattr(err, "slug", None) == "dummy"
    assert Path(getattr(err, "file_path", "")) == outside_pdf


def test_symlink_traversal_is_rejected(tmp_path: Path):
    base = tmp_path / "kb"
    cfg_dir = base / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    outside_pdf = tmp_path / "victim.pdf"
    outside_pdf.write_bytes(b"%PDF-1.4\n%\n")

    link = cfg_dir / "VisionStatement-link.pdf"
    _make_symlink(outside_pdf, link)

    from semantic.vision_provision import provision_from_vision as prov

    ctx = _Ctx(base)
    with pytest.raises(ConfigError) as ei:
        prov(ctx, _NoopLogger(), slug="dummy", pdf_path=link)
    err = ei.value
    assert getattr(err, "slug", None) == "dummy"
    # Il file_path dell'errore riporta il candidato (il symlink), non il target risolto
    assert Path(getattr(err, "file_path", "")) == link
