# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ui.services import vision_provision


def test_provision_requires_repo_root_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "ws"
    cfg = base / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    pdf = cfg / "VisionStatement.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")

    class _Ctx:
        def __init__(self) -> None:
            self.repo_root_dir = None

    def _fake_run_vision_with_gating(ctx: Any, logger: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("run_vision_with_gating non deve essere chiamato senza repo_root_dir")

    monkeypatch.setattr(vision_provision, "run_vision_with_gating", _fake_run_vision_with_gating)

    with pytest.raises(vision_provision.ConfigError) as excinfo:
        vision_provision.provision_from_vision_with_config(
            _Ctx(),
            logger=object(),
            slug="prova",
            pdf_path=pdf,
            force=True,
        )

    assert "repo_root_dir" in str(excinfo.value)
