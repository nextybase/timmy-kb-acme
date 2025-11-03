# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import ui.components.yaml_editors as yaml_editors


def test_write_yaml_text_syncs_tags_db(tmp_path, monkeypatch):
    workspace = tmp_path / "timmy-kb-dummy"
    semantic_dir = workspace / "semantic"
    semantic_dir.mkdir(parents=True)
    slug = "dummy"

    monkeypatch.setattr(yaml_editors, "workspace_root", lambda _slug: workspace)

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
