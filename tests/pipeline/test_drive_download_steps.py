# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from pipeline.workspace_layout import WorkspaceLayout


def _prepare_workspace(slug: str, workspace_root: Path) -> WorkspaceLayout:
    """Crea workspace minimo necessario per la validazione di WorkspaceLayout."""
    book_dir = workspace_root / "book"
    semantic_dir = workspace_root / "semantic"
    config_dir = workspace_root / "config"
    logs_dir = workspace_root / "logs"
    raw_dir = workspace_root / "raw"
    for path in (book_dir, semantic_dir, config_dir, logs_dir, raw_dir):
        path.mkdir(parents=True, exist_ok=True)
    (book_dir / "README.md").write_text("README", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("SUMMARY", encoding="utf-8")
    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    (semantic_dir / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    return WorkspaceLayout.from_workspace(workspace_root, slug=slug)


def test_download_with_progress_accepts_optional_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ui.services.drive_runner as dr

    ctx = SimpleNamespace(slug="dummy", redact_logs=False, env={"DRIVE_ID": "parent"})
    workspace_root = tmp_path / f"timmy-kb-{ctx.slug}"
    workspace_root.mkdir(parents=True, exist_ok=True)
    raw_dir = workspace_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    layout = _prepare_workspace(ctx.slug, workspace_root)

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
    monkeypatch.setattr(dr.WorkspaceLayout, "from_context", lambda *_a, **_k: layout)

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
