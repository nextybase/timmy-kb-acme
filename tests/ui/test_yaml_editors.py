# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import ui.components.yaml_editors as yaml_editors
from pipeline.workspace_layout import WorkspaceLayout


def test_write_yaml_text_syncs_tags_db(tmp_path, monkeypatch):
    slug = "dummy"
    workspace = tmp_path / f"timmy-kb-{slug}"
    semantic_dir = workspace / "semantic"
    config_dir = workspace / "config"
    book_dir = workspace / "book"
    raw_dir = workspace / "raw"
    logs_dir = workspace / "logs"
    for directory in (semantic_dir, config_dir, book_dir, raw_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text("client_name: dummy\n", encoding="utf-8")
    (book_dir / "README.md").write_text("# Book\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    layout = WorkspaceLayout.from_workspace(workspace=workspace, slug=slug)
    monkeypatch.setattr(
        yaml_editors,
        "get_ui_workspace_layout",
        lambda _slug, *, require_env=True: layout,
    )

    called: dict[str, Path] = {}

    def _fake_import(path: str | Path, **_kwargs):
        called["path"] = Path(path)
        return {}

    monkeypatch.setattr(yaml_editors, "import_tags_yaml_to_db", _fake_import)

    content = "version: 2\nkeep_only_listed: true\ntags: []\n"
    yaml_editors._write_yaml_text(slug, yaml_editors.TAGS_FILE, content)

    saved = (semantic_dir / yaml_editors.TAGS_FILE).read_text(encoding=yaml_editors.DEFAULT_ENCODING)
    assert saved == content
    assert called["path"] == semantic_dir / yaml_editors.TAGS_FILE
