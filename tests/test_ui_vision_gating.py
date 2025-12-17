# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError


class _Mem(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - banale
        self.records.append(record)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def test_ui_gating_hash_file_and_block_then_force(
    monkeypatch: pytest.MonkeyPatch,
    dummy_workspace,
    dummy_ctx,
    dummy_logger,
):
    import ui.services.vision_provision as VP

    base = dummy_workspace["base"]
    pdf = dummy_workspace["vision_pdf"]
    slug = dummy_workspace["slug"]
    mapping_path = dummy_workspace["semantic_mapping"]
    cartelle_path = dummy_workspace["cartelle_raw"]
    ctx = dummy_ctx
    logger = dummy_logger

    mem = _Mem()
    mem.setLevel(logging.INFO)
    logger.addHandler(mem)

    monkeypatch.delenv("VISION_MODEL", raising=False)

    hash_path = base / "semantic" / ".vision_hash"
    original_hash = hash_path.read_text(encoding="utf-8") if hash_path.exists() else None
    original_mapping = mapping_path.read_text(encoding="utf-8")
    original_cartelle = cartelle_path.read_text(encoding="utf-8")

    def _stub(*a, **k):
        return {
            "yaml_paths": {
                "mapping": str(mapping_path),
                "cartelle_raw": str(cartelle_path),
            }
        }

    monkeypatch.setattr(VP, "_provision_from_vision_with_config", _stub)

    try:
        res = VP.provision_from_vision_with_config(
            ctx,
            logger,
            slug=slug,
            pdf_path=pdf,
            model="test-model",
            force=False,
        )
        assert isinstance(res, dict)
        assert hash_path.exists()
        data = json.loads(hash_path.read_text(encoding="utf-8"))
        assert data.get("hash") == _sha256(pdf)
        assert data.get("model") == "test-model"

        gate = next((r for r in mem.records if r.msg == "ui.vision.gate"), None)
        upd = next((r for r in mem.records if r.msg == "ui.vision.update_hash"), None)
        assert gate is not None and getattr(gate, "hit", False) is False
        assert upd is not None and getattr(upd, "file_path", "").endswith(".vision_hash")

        with pytest.raises(ConfigError) as ei:
            VP.provision_from_vision_with_config(
                ctx,
                logger,
                slug=slug,
                pdf_path=pdf,
                model="test-model",
                force=False,
            )
        err = ei.value
        assert getattr(err, "slug", None) == slug
        assert Path(getattr(err, "file_path", "")) == hash_path

        res2 = VP.provision_from_vision_with_config(
            ctx,
            logger,
            slug=slug,
            pdf_path=pdf,
            model="test-model",
            force=True,
        )
        assert isinstance(res2, dict)
        data2 = json.loads(hash_path.read_text(encoding="utf-8"))
        assert data2.get("hash") == _sha256(pdf)
        assert data2.get("model") == "test-model"
    finally:
        logger.removeHandler(mem)
        if original_hash is None:
            if hash_path.exists():
                hash_path.unlink()
        else:
            hash_path.write_text(original_hash, encoding="utf-8")
        mapping_path.write_text(original_mapping, encoding="utf-8")
        cartelle_path.write_text(original_cartelle, encoding="utf-8")
