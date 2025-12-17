# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

from rosetta.client import RosettaConfig
from timmy_kb.cli.tag_onboarding_raw import _normalize_provider


def test_rosetta_disabled_by_default():
    cfg = RosettaConfig.load(repo_root=Path.cwd())
    assert not cfg.enabled


def test_ingest_provider_defaults_to_drive_when_no_override():
    assert _normalize_provider({}, "drive") == "drive"
    # skip_drive acts as fallback only when the source is not explicitly drive/local
    assert _normalize_provider({"skip_drive": True}, "unknown") == "local"
