# SPDX-License-Identifier: GPL-3.0-only
import logging
import sys
from types import SimpleNamespace

import pytest


def test_tag_onboarding_main_raises_configerror_when_drive_utils_missing(tmp_path, monkeypatch):
    """
    Quando l'import opzionale delle funzioni Drive fallisce (funzioni = None),
    il ramo source=="drive" deve sollevare ConfigError con istruzioni chiare,
    non TypeError da chiamata su None.
    """
    import timmykb.tag_onboarding as tag

    # Isola la root del workspace cliente
    client_root = tmp_path / "timmy-kb-dummy"
    (client_root / "config").mkdir(parents=True, exist_ok=True)
    # Config minimale con drive_raw_folder_id richiesto dal ramo drive
    (client_root / "config" / "config.yaml").write_text("drive_raw_folder_id: RAW_FOLDER_ID\n", encoding="utf-8")
    # Stub service account file richiesto dal contesto
    (client_root / "dummy.json").write_text(
        """
{
  "type": "service_account",
  "project_id": "dummy",
  "private_key_id": "abc",
  "private_key": "-----BEGIN PRIVATE KEY-----\\nMII...\\n-----END PRIVATE KEY-----\\n",
  "client_email": "dummy@project.iam.gserviceaccount.com",
  "client_id": "1234567890",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/dummy"
}
""".strip(),
        encoding="utf-8",
    )

    # Context di test minimale per evitare check env/drive
    fake_ctx = SimpleNamespace(
        slug="dummy",
        base_dir=client_root,
        raw_dir=client_root / "raw",
        md_dir=client_root / "book",
        config_path=client_root / "config" / "config.yaml",
        repo_root_dir=None,
        env={},
        run_id=None,
        redact_logs=False,
        service_account_file=client_root / "dummy.json",
    )
    fake_ctx.raw_dir.mkdir(parents=True, exist_ok=True)
    fake_ctx.md_dir.mkdir(parents=True, exist_ok=True)
    fake_resources = tag.ContextResources(
        context=fake_ctx,
        base_dir=client_root,
        raw_dir=fake_ctx.raw_dir,
        semantic_dir=client_root / "semantic",
        logger=logging.getLogger("test.tag.drive"),
        log_file=client_root / "logs" / "tag_onboarding.log",
    )
    fake_resources.semantic_dir.mkdir(parents=True, exist_ok=True)
    fake_resources.log_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tag, "prepare_context", lambda **kwargs: fake_resources)
    monkeypatch.setattr(
        "pipeline.drive.client.Credentials.from_service_account_file",
        lambda *a, **k: object(),
        raising=True,
    )

    # Simula funzioni mancanti dal modulo opzionale (sia modulo flat che namespaced)
    raw_mod = sys.modules.get("tag_onboarding_raw")
    if raw_mod is None:
        import tag_onboarding_raw as raw_mod  # type: ignore  # pragma: no cover
    monkeypatch.setattr(raw_mod, "get_drive_service", None, raising=False)
    monkeypatch.setattr(raw_mod, "download_drive_pdfs_to_local", None, raising=False)
    assert getattr(raw_mod, "get_drive_service") is None  # sanity: modulo flat patchato
    assert getattr(raw_mod, "download_drive_pdfs_to_local") is None
    package_raw_mod = sys.modules.get("timmykb.tag_onboarding_raw")
    if package_raw_mod is not None:
        monkeypatch.setattr(package_raw_mod, "get_drive_service", None, raising=False)
        monkeypatch.setattr(package_raw_mod, "download_drive_pdfs_to_local", None, raising=False)
        assert getattr(package_raw_mod, "get_drive_service") is None
        assert getattr(package_raw_mod, "download_drive_pdfs_to_local") is None

    with pytest.raises(tag.ConfigError) as exc:
        tag.tag_onboarding_main(
            slug="dummy",
            source="drive",
            non_interactive=True,
            proceed_after_csv=False,
        )
    msg = str(exc.value).lower()
    assert "pip install" in msg and "drive" in msg
