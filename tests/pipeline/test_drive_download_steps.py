# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest


def test_download_with_progress_accepts_optional_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ui.services.drive_runner as dr

    ctx = SimpleNamespace(slug="dummy", redact_logs=False, env={"DRIVE_ID": "parent"})
    workspace_root = tmp_path / f"timmy-kb-{ctx.slug}"
    workspace_root.mkdir(parents=True, exist_ok=True)
    raw_dir = workspace_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dr, "get_client_context", lambda *_a, **_k: ctx)
    monkeypatch.setattr(dr, "get_drive_service", lambda _ctx: object())
    monkeypatch.setattr(dr, "_get_existing_client_folder_id", lambda *_a, **_k: "CFID")
    monkeypatch.setattr(
        dr,
        "_drive_list_folders",
        lambda _svc, folder_id: [{"name": "raw", "id": "RAW"}] if folder_id == "CFID" else [],
    )
    monkeypatch.setattr(dr, "_drive_list_pdfs", lambda *_a, **_k: [])
    monkeypatch.setattr(dr, "discover_candidates", lambda **_k: [])
    monkeypatch.setattr(dr, "snapshot_existing", lambda _c: set())
    monkeypatch.setattr(dr, "compute_created", lambda _c, _b: [])
    monkeypatch.setattr(dr, "emit_progress", lambda *_a, **_k: None)
    monkeypatch.setattr(dr, "_resolve_workspace", lambda base_root, slug: workspace_root)

    captured: Dict[str, Any] = {}

    def fake_downloader(
        service: Any,
        remote_root_folder_id: str,
        local_root_dir: str,
        *,
        progress,
        context,
        redact_logs: bool,
        chunk_size: int,
        overwrite: bool,
    ) -> int:
        captured.update(
            {
                "local_root_dir": local_root_dir,
                "overwrite": overwrite,
            }
        )
        return 0

    monkeypatch.setattr(dr, "download_drive_pdfs_to_local", fake_downloader)

    written = dr.download_raw_from_drive_with_progress(
        slug=ctx.slug,
        base_root=tmp_path,
        require_env=False,
        overwrite=None,
        on_progress=None,
    )

    assert written == []
    assert captured["overwrite"] is False
    assert Path(captured["local_root_dir"]).resolve() == raw_dir.resolve()
