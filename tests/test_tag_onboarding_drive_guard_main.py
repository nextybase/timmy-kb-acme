import pytest


def test_tag_onboarding_main_raises_configerror_when_drive_utils_missing(tmp_path, monkeypatch):
    """
    Quando l'import opzionale delle funzioni Drive fallisce (funzioni = None),
    il ramo source=="drive" deve sollevare ConfigError con istruzioni chiare,
    non TypeError da chiamata su None.
    """
    import src.tag_onboarding as tag

    # Isola la root del workspace cliente
    client_root = tmp_path / "timmy-kb-smk"
    (client_root / "config").mkdir(parents=True, exist_ok=True)
    # Config minimale con drive_raw_folder_id richiesto dal ramo drive
    (client_root / "config" / "config.yaml").write_text("drive_raw_folder_id: RAW_FOLDER_ID\n", encoding="utf-8")

    # Env richieste quando require_env=True
    monkeypatch.setenv("REPO_ROOT_DIR", str(client_root))
    monkeypatch.setenv("SERVICE_ACCOUNT_FILE", "dummy.json")
    monkeypatch.setenv("DRIVE_ID", "dummy-drive-id")

    # Simula funzioni mancanti dal modulo opzionale
    monkeypatch.setattr(tag, "get_drive_service", None, raising=False)
    monkeypatch.setattr(tag, "download_drive_pdfs_to_local", None, raising=False)

    with pytest.raises(tag.ConfigError) as exc:
        tag.tag_onboarding_main(
            slug="smk",
            source="drive",
            non_interactive=True,
            proceed_after_csv=False,
        )
    msg = str(exc.value)
    assert "pip install" in msg and "drive" in msg.lower()
