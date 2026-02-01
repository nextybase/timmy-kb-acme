# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from ai.types import AssistantConfig
from pipeline.exceptions import ConfigError
from semantic.vision_provision import provision_from_vision_with_config


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def warning(self, *args, **kwargs):
        pass


class _Ctx:
    def __init__(self, repo_root_dir: Path):
        self.repo_root_dir = str(repo_root_dir)


def _make_symlink(src: Path, dst: Path) -> None:
    try:
        dst.symlink_to(src)
    except OSError as e:  # pragma: no cover - piattaforme senza permessi symlink
        pytest.skip(f"symlink not supported on this platform: {e}")


def _dummy_config() -> AssistantConfig:
    return AssistantConfig(
        model="test-model",
        assistant_id="asst",
        assistant_env="OBNEXT_ASSISTANT_ID",
        use_kb=True,
        strict_output=True,
    )


def test_pdf_path_outside_base_dir_is_rejected_with_slug_and_file(tmp_path: Path):
    base = tmp_path / "kb"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    outside_pdf = tmp_path / "outside.pdf"
    outside_pdf.write_bytes(b"%PDF-1.4\n%\n")

    ctx = _Ctx(base)
    with pytest.raises(ConfigError) as ei:
        provision_from_vision_with_config(
            ctx,
            _NoopLogger(),
            slug="dummy",
            pdf_path=outside_pdf,
            config=_dummy_config(),
            retention_days=0,
        )
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

    ctx = _Ctx(base)
    with pytest.raises(ConfigError) as ei:
        provision_from_vision_with_config(
            ctx,
            _NoopLogger(),
            slug="dummy",
            pdf_path=link,
            config=_dummy_config(),
            retention_days=0,
        )
    err = ei.value
    assert getattr(err, "slug", None) == "dummy"
    # Il file_path dell'errore riporta il candidato (il symlink), non il target risolto
    assert Path(getattr(err, "file_path", "")) == link
