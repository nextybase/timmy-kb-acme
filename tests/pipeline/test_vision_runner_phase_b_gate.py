# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, WorkspaceLayoutInvalid
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.vision_runner import run_vision_with_gating


def _write_text(base: Path, target: Path, text: str) -> None:
    safe_path = ensure_within_and_resolve(base, target)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(safe_path, text, encoding="utf-8", atomic=True)


def _workspace(tmp_path: Path, *, with_mapping: bool) -> Path:
    base = tmp_path / "workspace"
    base.mkdir(parents=True, exist_ok=True)
    for name in ("raw", "normalized", "semantic", "logs", "book", "config"):
        (base / name).mkdir(parents=True, exist_ok=True)
    _write_text(base, base / "config" / "config.yaml", "client_name: Test\n")
    _write_text(base, base / "book" / "README.md", "# Test\n")
    _write_text(base, base / "book" / "SUMMARY.md", "* [Intro](intro.md)\n")
    if with_mapping:
        _write_text(base, base / "semantic" / "semantic_mapping.yaml", "areas:\n  - key: Area One\n")
    return base


def _ctx(base: Path) -> ClientContext:
    return ClientContext(
        slug="acme",
        repo_root_dir=base,
        config_path=base / "config" / "config.yaml",
        mapping_path=base / "semantic" / "semantic_mapping.yaml",
    )


def _write_sentinel(base: Path, *, digest: str, model: str | None) -> None:
    payload = {"hash": digest, "ts": "2026-01-01T00:00:00Z"}
    if model is not None:
        payload["model"] = model
    _write_text(base, base / "semantic" / ".vision_hash", json.dumps(payload) + "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _logger() -> logging.Logger:
    log = logging.getLogger("test.vision.phase_b_gate")
    log.setLevel(logging.INFO)
    if not log.handlers:
        log.addHandler(logging.NullHandler())
    return log


def test_run_vision_with_gating_requires_phase_b_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _workspace(tmp_path, with_mapping=False)
    ctx = _ctx(base)
    pdf_path = base / "config" / "VisionStatement.pdf"
    _write_text(base, pdf_path, "dummy pdf bytes")

    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_config", lambda *_a, **_k: SimpleNamespace(model="m"))
    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_retention_days", lambda *_a, **_k: 30)
    monkeypatch.setattr(
        "pipeline.vision_runner._provision_from_vision_with_config",
        lambda **_k: {"mapping": "semantic/semantic_mapping.yaml"},
    )

    with pytest.raises(WorkspaceLayoutInvalid) as excinfo:
        run_vision_with_gating(ctx, _logger(), slug="acme", pdf_path=pdf_path)
    assert "semantic/semantic_mapping.yaml" in str(excinfo.value)


def test_run_vision_with_gating_proceeds_when_phase_b_mapping_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _workspace(tmp_path, with_mapping=True)
    ctx = _ctx(base)
    pdf_path = base / "config" / "VisionStatement.pdf"
    _write_text(base, pdf_path, "dummy pdf bytes")

    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_config", lambda *_a, **_k: SimpleNamespace(model="m"))
    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_retention_days", lambda *_a, **_k: 30)
    monkeypatch.setattr(
        "pipeline.vision_runner._provision_from_vision_with_config",
        lambda **_k: {"mapping": "semantic/semantic_mapping.yaml"},
    )
    monkeypatch.setattr(
        "pipeline.vision_runner.get_client_config",
        lambda _ctx: {"integrations": {"drive": {"raw_folder_id": "raw-id"}}},
    )
    monkeypatch.setattr(
        "pipeline.vision_runner.create_drive_structure_from_names",
        lambda **kwargs: list(kwargs.get("folder_names") or []),
    )

    result = run_vision_with_gating(ctx, _logger(), slug="acme", pdf_path=pdf_path)

    assert result["skipped"] is False
    assert (base / "raw" / "area-one").is_dir()


def test_run_vision_with_gating_skips_provision_on_hash_and_model_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _workspace(tmp_path, with_mapping=True)
    ctx = _ctx(base)
    pdf_path = base / "config" / "VisionStatement.pdf"
    _write_text(base, pdf_path, "dummy pdf bytes")
    digest = _sha256(pdf_path)
    _write_sentinel(base, digest=digest, model="m")

    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_config", lambda *_a, **_k: SimpleNamespace(model="m"))
    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_retention_days", lambda *_a, **_k: 30)
    monkeypatch.setattr(
        "pipeline.vision_runner._provision_from_vision_with_config",
        lambda **_k: (_ for _ in ()).throw(AssertionError("provision non deve essere chiamata su gate hit")),
    )
    monkeypatch.setattr(
        "pipeline.vision_runner.get_client_config",
        lambda _ctx: {"integrations": {"drive": {"raw_folder_id": "raw-id"}}},
    )
    monkeypatch.setattr(
        "pipeline.vision_runner.create_drive_structure_from_names",
        lambda **kwargs: list(kwargs.get("folder_names") or []),
    )

    result = run_vision_with_gating(ctx, _logger(), slug="acme", pdf_path=pdf_path)

    assert result["skipped"] is True
    assert result["hash"] == digest
    assert result["mapping"] == str(base / "semantic" / "semantic_mapping.yaml")


def test_run_vision_with_gating_model_mismatch_calls_provision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _workspace(tmp_path, with_mapping=True)
    ctx = _ctx(base)
    pdf_path = base / "config" / "VisionStatement.pdf"
    _write_text(base, pdf_path, "dummy pdf bytes")
    digest = _sha256(pdf_path)
    _write_sentinel(base, digest=digest, model="old-model")

    calls = {"provision": 0}

    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_config", lambda *_a, **_k: SimpleNamespace(model="m"))
    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_retention_days", lambda *_a, **_k: 30)

    def _provision(**_k):
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

    result = run_vision_with_gating(ctx, _logger(), slug="acme", pdf_path=pdf_path)

    assert calls["provision"] == 1
    assert result["skipped"] is False


def test_run_vision_with_gating_gate_hit_propagates_typeerror_from_mapping_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _workspace(tmp_path, with_mapping=True)
    ctx = _ctx(base)
    pdf_path = base / "config" / "VisionStatement.pdf"
    _write_text(base, pdf_path, "dummy pdf bytes")
    digest = _sha256(pdf_path)
    _write_sentinel(base, digest=digest, model="m")

    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_config", lambda *_a, **_k: SimpleNamespace(model="m"))
    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_retention_days", lambda *_a, **_k: 30)
    monkeypatch.setattr(
        "pipeline.vision_runner._provision_from_vision_with_config",
        lambda **_k: (_ for _ in ()).throw(AssertionError("provision non deve essere chiamata su gate hit")),
    )
    monkeypatch.setattr(
        "pipeline.vision_runner._mapping_metrics",
        lambda *_a, **_k: (_ for _ in ()).throw(TypeError("boom")),
    )

    with pytest.raises(TypeError, match="boom"):
        run_vision_with_gating(ctx, _logger(), slug="acme", pdf_path=pdf_path)


def test_run_vision_with_gating_gate_hit_wraps_valueerror_from_mapping_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _workspace(tmp_path, with_mapping=True)
    ctx = _ctx(base)
    pdf_path = base / "config" / "VisionStatement.pdf"
    _write_text(base, pdf_path, "dummy pdf bytes")
    digest = _sha256(pdf_path)
    _write_sentinel(base, digest=digest, model="m")

    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_config", lambda *_a, **_k: SimpleNamespace(model="m"))
    monkeypatch.setattr("pipeline.vision_runner.resolve_vision_retention_days", lambda *_a, **_k: 30)
    monkeypatch.setattr(
        "pipeline.vision_runner._provision_from_vision_with_config",
        lambda **_k: (_ for _ in ()).throw(AssertionError("provision non deve essere chiamata su gate hit")),
    )
    monkeypatch.setattr(
        "pipeline.vision_runner._mapping_metrics",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad-mapping")),
    )

    with pytest.raises(ConfigError, match="semantic_mapping.yaml non leggibile"):
        run_vision_with_gating(ctx, _logger(), slug="acme", pdf_path=pdf_path)
