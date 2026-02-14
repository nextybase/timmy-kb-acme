# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.context import ClientContext
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.vision_runner import _load_last_hash, run_vision_with_gating


def _write_text(base: Path, target: Path, text: str) -> None:
    safe_path = ensure_within_and_resolve(base, target)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(safe_path, text, encoding="utf-8", atomic=True)


def _workspace(tmp_path: Path) -> Path:
    base = tmp_path / "workspace"
    base.mkdir(parents=True, exist_ok=True)
    for name in ("raw", "normalized", "semantic", "logs", "book", "config"):
        (base / name).mkdir(parents=True, exist_ok=True)
    _write_text(base, base / "config" / "config.yaml", "client_name: Test\n")
    _write_text(base, base / "book" / "README.md", "# Test\n")
    _write_text(base, base / "book" / "SUMMARY.md", "* [Intro](intro.md)\n")
    _write_text(base, base / "semantic" / "semantic_mapping.yaml", "areas:\n  - key: Area One\n")
    return base


def _ctx(base: Path) -> ClientContext:
    return ClientContext(
        slug="acme",
        repo_root_dir=base,
        config_path=base / "config" / "config.yaml",
        mapping_path=base / "semantic" / "semantic_mapping.yaml",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_last_hash_valid_sentinel(tmp_path: Path) -> None:
    base = _workspace(tmp_path)
    sentinel = base / "semantic" / ".vision_hash"
    payload = {"hash": "a" * 64, "model": "m", "ts": "2026-01-01T00:00:00Z"}
    _write_text(base, sentinel, json.dumps(payload) + "\n")

    result = _load_last_hash(base, slug="acme")

    assert result == payload


def test_load_last_hash_invalid_sentinel_forces_rerun_and_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = _workspace(tmp_path)
    sentinel = base / "semantic" / ".vision_hash"
    # Hash invalido: troppo lungo, non conforme a sha256 hexdigest.
    payload = {"hash": "x" * 512, "model": "m", "ts": "2026-01-01T00:00:00Z"}
    _write_text(base, sentinel, json.dumps(payload) + "\n")

    caplog.set_level(logging.WARNING, logger="pipeline.vision_runner")
    result = _load_last_hash(base, slug="acme")

    assert result == {}
    assert any(record.message == "vision.hash_sentinel_invalid" for record in caplog.records), caplog.text


def test_invalid_sentinel_triggers_rerun_in_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _workspace(tmp_path)
    ctx = _ctx(base)
    pdf_path = base / "config" / "VisionStatement.pdf"
    _write_text(base, pdf_path, "dummy pdf bytes")

    # Sentinel presente ma invalido => deve comportarsi come hash mismatch e rieseguire provision.
    sentinel = base / "semantic" / ".vision_hash"
    payload = {"hash": "x" * 512, "model": "m", "ts": "2026-01-01T00:00:00Z"}
    _write_text(base, sentinel, json.dumps(payload) + "\n")

    calls = {"provision": 0}
    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_config", lambda *_a, **_k: SimpleNamespace(model="m"))
    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_retention_days", lambda *_a, **_k: 30)

    def _provision(**_k: object) -> dict[str, str]:
        calls["provision"] += 1
        return {"mapping": "semantic/semantic_mapping.yaml"}

    monkeypatch.setattr("pipeline.vision_runner._provision_from_vision_with_config", _provision)
    monkeypatch.setattr(
        "pipeline.vision_runner.get_client_config",
        lambda _ctx: {"integrations": {"drive": {"raw_folder_id": "raw-id"}}},
    )
    monkeypatch.setattr(
        "pipeline.vision_runner.create_drive_structure_from_names",
        lambda **kwargs: list(kwargs.get("folder_names") or []),
    )

    result = run_vision_with_gating(ctx, logging.getLogger("test.vision.hash.invalid"), slug="acme", pdf_path=pdf_path)

    assert calls["provision"] == 1
    assert result["skipped"] is False
    assert result["hash"] == _sha256(pdf_path)
