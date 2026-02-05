# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from types import SimpleNamespace

import pytest

from pipeline.exceptions import CapabilityUnavailableError
from pipeline.ingest import provider as ingest_provider
from tests._helpers.workspace_paths import local_workspace_dir
from timmy_kb.cli import tag_onboarding_raw as raw_mod


def test_tag_onboarding_main_raises_capability_error_when_drive_utils_missing(tmp_path, monkeypatch):
    """
    Quando l'import opzionale delle funzioni Drive fallisce (funzioni = None),
    il ramo source=="drive" deve sollevare ConfigError con istruzioni chiare,
    non TypeError da chiamata su None.
    """
    client_root = local_workspace_dir(tmp_path, "dummy")
    raw_dir = client_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    fake_ctx = SimpleNamespace(
        slug="dummy",
        settings={"integrations": {"drive": {"raw_folder_id": "RAW_FOLDER_ID"}}},
    )

    monkeypatch.setattr(ingest_provider, "get_drive_service", None)
    monkeypatch.setattr(ingest_provider, "download_drive_pdfs_to_local", None)

    with pytest.raises(CapabilityUnavailableError) as exc:
        raw_mod.download_from_drive(
            context=fake_ctx,
            logger=logging.getLogger("test.tag.drive"),
            raw_dir=raw_dir,
            non_interactive=True,
        )

    msg = str(exc.value).lower()
    assert "drive capability" in msg
