# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

from pipeline.file_utils import safe_write_text
from pipeline.ownership import ensure_ownership_file, load_ownership


def _write_template(base: Path, text: str) -> None:
    template_path = base / "clients" / "example" / "ownership.yaml"
    safe_write_text(template_path, text, encoding="utf-8")


def test_ensure_ownership_file_creates_from_template(tmp_path):
    slug = "tenant123"
    template_content = 'schema_version: "1"'
    template_dir = tmp_path / "clients" / "example"
    template_dir.mkdir(parents=True, exist_ok=True)
    _write_template(tmp_path, template_content)

    created = ensure_ownership_file(slug, tmp_path)

    assert created.exists()
    cfg = load_ownership(slug, tmp_path)
    assert cfg["slug"] == slug


def test_ensure_ownership_file_keeps_existing(tmp_path):
    slug = "tenant123"
    target = tmp_path / "clients" / slug / "ownership.yaml"
    safe_write_text(target, 'schema_version: "1"\nslug: existing', encoding="utf-8")

    result = ensure_ownership_file(slug, tmp_path)
    assert result.exists()
    assert target.read_text(encoding="utf-8").strip().startswith("schema_version")
