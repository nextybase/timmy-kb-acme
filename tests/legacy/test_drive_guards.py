import pytest


def test_require_drive_utils_raises_when_missing(monkeypatch):
    import timmykb.pre_onboarding as pre

    # Simula funzioni drive mancanti
    monkeypatch.setattr(pre, "get_drive_service", None, raising=False)
    monkeypatch.setattr(pre, "create_drive_folder", None, raising=False)
    monkeypatch.setattr(pre, "create_drive_structure_from_yaml", None, raising=False)
    monkeypatch.setattr(pre, "upload_config_to_drive_folder", None, raising=False)

    with pytest.raises(pre.ConfigError) as exc:
        pre._require_drive_utils()
    msg = str(exc.value)
    assert "pip install" in msg and "drive" in msg.lower()


def test_require_drive_utils_passes_when_callable(monkeypatch):
    import timmykb.pre_onboarding as pre

    # Fornisce stub callabili
    monkeypatch.setattr(pre, "get_drive_service", lambda ctx: object(), raising=False)
    monkeypatch.setattr(pre, "create_drive_folder", lambda *a, **k: "id", raising=False)
    monkeypatch.setattr(pre, "create_drive_structure_from_yaml", lambda *a, **k: {}, raising=False)
    monkeypatch.setattr(pre, "upload_config_to_drive_folder", lambda *a, **k: "id", raising=False)

    # Non deve sollevare
    pre._require_drive_utils()


def test_ui_drive_runner_guard(monkeypatch):
    import timmykb.ui.services.drive_runner as dr

    # Simula funzioni mancanti
    monkeypatch.setattr(dr, "get_drive_service", None, raising=False)
    monkeypatch.setattr(dr, "create_drive_folder", None, raising=False)
    monkeypatch.setattr(dr, "create_drive_structure_from_yaml", None, raising=False)
    monkeypatch.setattr(dr, "upload_config_to_drive_folder", None, raising=False)

    with pytest.raises(RuntimeError) as exc:
        dr._require_drive_utils_ui()
    assert "pip install" in str(exc.value)


def test_tag_onboarding_guard(monkeypatch):
    import timmykb.tag_onboarding as tag

    monkeypatch.setattr(tag, "get_drive_service", None, raising=False)
    monkeypatch.setattr(tag, "download_drive_pdfs_to_local", None, raising=False)

    with pytest.raises(tag.ConfigError) as exc:
        tag._require_drive_utils()
    assert "pip install" in str(exc.value)
