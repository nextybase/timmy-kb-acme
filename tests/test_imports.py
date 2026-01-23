# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import types

import pytest


def test_import_drive_utils_no_bom() -> None:
    """Import drive_utils o fallisce chiaramente se mancano dipendenze."""
    importlib.invalidate_caches()
    try:
        mod = importlib.import_module("pipeline.drive_utils")
    except ImportError as e:
        assert "google" in str(e).lower() or "drive" in str(e).lower()
        return
    assert isinstance(mod, types.ModuleType)
    assert mod.__doc__ is not None and len(mod.__doc__) > 0
    assert hasattr(mod, "__all__")


def test_reexports_present() -> None:
    """Controlla i simboli pubblici solo quando il modulo è importabile."""
    try:
        mod = importlib.import_module("pipeline.drive_utils")
    except ImportError:
        pytest.skip("googleapiclient non installato: modulo non importabile (no fallback)")
    expected = {
        "get_drive_service",
        "list_drive_files",
        "get_file_metadata",
        "create_drive_folder",
        "create_drive_minimal_structure",
        "upload_config_to_drive_folder",
        "delete_drive_file",
        "download_drive_pdfs_to_local",
    }
    missing = [name for name in expected if not hasattr(mod, name)]
    assert not missing, f"Simboli mancanti nella facciata drive_utils: {missing}"
