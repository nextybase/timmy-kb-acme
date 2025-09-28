from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger


class _Mem(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - banale
        self.records.append(record)


class _Ctx:
    def __init__(self, base_dir: Path):
        self.base_dir = str(base_dir)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture()
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "kb"
    (base / "config").mkdir(parents=True, exist_ok=True)
    pdf = base / "config" / "VisionStatement.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%\nHello")
    return base, pdf


def test_ui_gating_hash_file_and_block_then_force(monkeypatch: pytest.MonkeyPatch, workspace: tuple[Path, Path]):
    base, pdf = workspace
    ctx = _Ctx(base)

    # Logger strutturato con memoria
    logger = get_structured_logger("test.ui.vision")
    mem = _Mem()
    mem.setLevel(logging.INFO)
    logger.addHandler(mem)

    # Assicura che ENV non interferisca con il modello effettivo
    monkeypatch.delenv("VISION_MODEL", raising=False)

    # Stub provisioning semantico per evitare rete/SDK
    import ui.services.vision_provision as VP

    def _stub(*a, **k):
        return {"yaml_paths": {"mapping": "m", "cartelle_raw": "c"}}

    monkeypatch.setattr(VP, "_provision_from_vision", _stub)

    # Primo run: crea .vision_hash
    res = VP.provision_from_vision(ctx, logger, slug="acme", pdf_path=pdf, model="test-model", force=False)
    assert isinstance(res, dict)
    h_path = base / "semantic" / ".vision_hash"
    assert h_path.exists()
    data = json.loads(h_path.read_text(encoding="utf-8"))
    assert data.get("hash") == _sha256(pdf)
    assert data.get("model") == "test-model"

    # Verifica logging gate+update
    gate = next((r for r in mem.records if r.msg == "ui.vision.gate"), None)
    upd = next((r for r in mem.records if r.msg == "ui.vision.update_hash"), None)
    assert gate is not None and getattr(gate, "hit", False) is False
    assert upd is not None and getattr(upd, "file_path", "").endswith(".vision_hash")

    # Secondo run senza force: blocco
    with pytest.raises(ConfigError) as ei:
        VP.provision_from_vision(ctx, logger, slug="acme", pdf_path=pdf, model="test-model", force=False)
    err = ei.value
    assert getattr(err, "slug", None) == "acme"
    assert Path(getattr(err, "file_path", "")).name == ".vision_hash"

    # Terzo run con force: procede e riscrive .vision_hash
    res2 = VP.provision_from_vision(ctx, logger, slug="acme", pdf_path=pdf, model="test-model", force=True)
    assert isinstance(res2, dict)
    data2 = json.loads(h_path.read_text(encoding="utf-8"))
    assert data2.get("hash") == _sha256(pdf)
    assert data2.get("model") == "test-model"
