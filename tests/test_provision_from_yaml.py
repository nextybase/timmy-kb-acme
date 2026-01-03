# SPDX-License-Identifier: GPL-3.0-only
# tests/test_provision_from_yaml.py
from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore

from pipeline.exceptions import ConfigError
from pipeline.provision_from_yaml import provision_directories_from_cartelle_raw


class _NoopLogger:
    def info(self, *args, **kwargs): ...

    def error(self, *args, **kwargs): ...

    def exception(self, *args, **kwargs): ...
    def warning(self, *args, **kwargs): ...


class DummyCtx:
    def __init__(self, base_dir: Path):
        self.base_dir = str(base_dir)


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "output" / "timmy-kb-dummy"
    for folder in ("docs", "semantic"):
        (base / folder).mkdir(parents=True, exist_ok=True)
    return base


def _write_yaml(base: Path, filename: str, payload: dict) -> Path:
    target = base / "semantic" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return target


def test_happy_path_crea_directories(tmp_workspace: Path, tmp_path: Path):
    yaml_payload = {
        "version": 1,
        "source": "vision",
        "context": {"slug": "dummy"},
        "folders": [
            {"key": "artefatti-operativi", "title": "operativo"},
            {"key": "governance", "title": "strategico"},
            {"key": "progetti", "title": "progetti"},
        ],
    }
    ypath = _write_yaml(tmp_workspace, "cartelle_raw.yaml", yaml_payload)

    ctx = DummyCtx(base_dir=tmp_workspace)
    res = provision_directories_from_cartelle_raw(ctx, _NoopLogger(), slug="dummy", yaml_path=ypath)

    docs_dir = tmp_workspace / "docs"
    assert (docs_dir / "artefatti-operativi").exists()
    assert (docs_dir / "governance").exists()
    assert (docs_dir / "progetti").exists()
    assert len(res["created"]) == 3
    assert len(res["skipped"]) == 0


def test_duplicate_keys_go_to_skipped(tmp_workspace: Path, tmp_path: Path):
    yaml_payload = {
        "version": 1,
        "source": "vision",
        "context": {"slug": "dummy"},
        "folders": [
            {"key": "governance", "title": "strategico"},
            {"key": "governance", "title": "strategico-dup"},
        ],
    }
    ypath = _write_yaml(tmp_workspace, "cartelle_raw.yaml", yaml_payload)

    ctx = DummyCtx(base_dir=tmp_workspace)
    res = provision_directories_from_cartelle_raw(ctx, _NoopLogger(), slug="dummy", yaml_path=ypath)

    docs_dir = tmp_workspace / "docs"
    assert (docs_dir / "governance").exists()
    # uno creato, uno skipped per duplicato
    assert len(res["created"]) == 1
    assert len(res["skipped"]) == 1


@pytest.mark.parametrize(
    "payload, msg",
    [
        ({}, "version"),
        ({"version": 1}, "folders"),
        ({"version": 1, "folders": []}, "folders"),
        ({"version": 1, "folders": [{}]}, "key"),
        ({"version": 1, "folders": [{"key": "a"}]}, "title"),
    ],
)
def test_invalid_yaml_raises_config_error(tmp_workspace: Path, tmp_path: Path, payload: dict, msg: str):
    ypath = _write_yaml(tmp_workspace, "bad.yaml", payload)
    ctx = DummyCtx(base_dir=tmp_workspace)
    with pytest.raises(ConfigError) as exc:
        provision_directories_from_cartelle_raw(ctx, _NoopLogger(), slug="dummy", yaml_path=ypath)
    assert msg in str(exc.value)
