# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from pipeline.config_utils import _LEGACY_DRIVE_KEY_MAP as LEGACY_DRIVE_KEY_MAP
from pipeline.config_utils import update_config_with_drive_ids
from pipeline.context import ClientContext
from pipeline.file_utils import safe_write_text
from pipeline.yaml_utils import yaml_read


def _make_context(tmp_path: Path, slug: str = "acme") -> ClientContext:
    base = tmp_path / f"timmy-kb-{slug}"
    config_path = base / "config" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    for name in ("raw", "normalized", "semantic", "logs", "book"):
        (base / name).mkdir(parents=True, exist_ok=True)
    safe_write_text(base / "book" / "README.md", "# Test\n", encoding="utf-8", atomic=True)
    safe_write_text(base / "book" / "SUMMARY.md", "* [Intro](intro.md)\n", encoding="utf-8", atomic=True)
    safe_write_text(config_path, "client_name: Test\n", encoding="utf-8", atomic=True)
    return ClientContext(slug=slug, repo_root_dir=base, config_path=config_path, settings=None)


def _read_config(config_path: Path) -> dict:
    data = yaml_read(config_path.parent, config_path) or {}
    return dict(data) if isinstance(data, dict) else {}


def test_pre_onboarding_updates_write_nested_only(tmp_path: Path) -> None:
    ctx = _make_context(tmp_path)
    updates = {
        "integrations": {
            "drive": {
                "folder_id": "fid",
                "raw_folder_id": "rid",
                "contrattualistica_folder_id": "cid",
                "config_folder_id": "cfgid",
            }
        }
    }
    update_config_with_drive_ids(ctx, updates, logger=logging.getLogger("test.config.migrate"))

    cfg = _read_config(ctx.config_path)
    drive = cfg.get("integrations", {}).get("drive", {})
    assert drive.get("folder_id") == "fid"
    assert drive.get("raw_folder_id") == "rid"
    for legacy_key in LEGACY_DRIVE_KEY_MAP:
        assert legacy_key not in cfg


def test_migration_from_flat_to_nested(tmp_path: Path) -> None:
    ctx = _make_context(tmp_path)
    legacy_payload = {
        legacy_key: value
        for legacy_key, value in zip(LEGACY_DRIVE_KEY_MAP, ("root", "raw", "contr", "cfg"), strict=False)
    }
    yaml_dump = yaml.safe_dump(legacy_payload, sort_keys=False)
    safe_write_text(ctx.config_path, yaml_dump, encoding="utf-8", atomic=True)

    update_config_with_drive_ids(ctx, updates={}, logger=logging.getLogger("test.config.migrate"))

    cfg = _read_config(ctx.config_path)
    drive = cfg.get("integrations", {}).get("drive", {})
    assert drive.get("folder_id") == "root"
    assert drive.get("raw_folder_id") == "raw"
    for legacy_key in LEGACY_DRIVE_KEY_MAP:
        assert legacy_key not in cfg


def test_vision_statement_pdf_location(tmp_path: Path) -> None:
    ctx = _make_context(tmp_path)
    safe_write_text(
        ctx.config_path,
        "meta:\n  vision_statement_pdf: config/VisionStatement.pdf\n",
        encoding="utf-8",
        atomic=True,
    )

    update_config_with_drive_ids(ctx, updates={}, logger=logging.getLogger("test.config.vision"))

    cfg = _read_config(ctx.config_path)
    vision = cfg.get("ai", {}).get("vision", {})
    assert vision.get("vision_statement_pdf") == "config/VisionStatement.pdf"
    assert "vision_statement_pdf" not in cfg
