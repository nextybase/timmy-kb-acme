# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ui.services import vision_provision


def test_provision_infers_base_dir_from_pdf_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "ws"
    cfg = base / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    pdf = cfg / "VisionStatement.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")

    class _Ctx:
        def __init__(self) -> None:
            self.base_dir = None

    seen: dict[str, Any] = {}

    def _fake_run_vision_with_gating(ctx: Any, logger: Any, **kwargs: Any) -> dict[str, Any]:
        seen["base_dir"] = getattr(ctx, "base_dir", None)
        return {"ok": True}

    monkeypatch.setattr(vision_provision, "run_vision_with_gating", _fake_run_vision_with_gating)

    out = vision_provision.provision_from_vision_with_config(
        _Ctx(),
        logger=object(),
        slug="prova",
        pdf_path=pdf,
        force=True,
    )

    assert out["ok"] is True
    assert Path(seen["base_dir"]) == base
