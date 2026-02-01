# SPDX-License-Identifier: GPL-3.0-or-later
import pytest


def test_emit_readmes_guard_when_drive_utils_missing(monkeypatch):
    import ui.services.drive_runner as dr

    # Simula funzioni pipeline drive mancanti
    monkeypatch.setattr(dr, "get_drive_service", None, raising=False)
    monkeypatch.setattr(dr, "create_drive_folder", None, raising=False)
    monkeypatch.setattr(dr, "upload_config_to_drive_folder", None, raising=False)

    with pytest.raises(RuntimeError) as exc:
        dr.emit_readmes_for_raw("smk", base_root="output", require_env=False)
    assert "pip install" in str(exc.value) and "drive" in str(exc.value).lower()


def test_download_with_progress_guard_when_drive_utils_missing(monkeypatch):
    import ui.services.drive_runner as dr

    # Simula funzioni pipeline drive mancanti
    monkeypatch.setattr(dr, "get_drive_service", None, raising=False)
    monkeypatch.setattr(dr, "create_drive_folder", None, raising=False)
    monkeypatch.setattr(dr, "download_drive_pdfs_to_local", None, raising=False)

    with pytest.raises(RuntimeError) as exc:
        dr.download_raw_from_drive_with_progress("smk", base_root="output", require_env=False, on_progress=None)
    assert "pip install" in str(exc.value) and "drive" in str(exc.value).lower()
