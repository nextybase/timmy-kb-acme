from pathlib import Path

import pytest


def test_download_with_progress_adapter(monkeypatch, tmp_path):
    import logging

    # Evita 'src.' nel nome modulo per non duplicare path in mypy
    import ui.services.drive_runner as dr

    # Fake ClientContext
    class Ctx:
        slug = "dummy"
        redact_logs = False
        env = {"DRIVE_ID": "PARENT"}

    monkeypatch.setattr(dr, "ClientContext", type("_C", (), {"load": staticmethod(lambda **_: Ctx())}))

    # Fake Drive service and helpers
    class Svc:
        pass

    monkeypatch.setattr(dr, "get_drive_service", lambda ctx: Svc())
    monkeypatch.setattr(dr, "_get_existing_client_folder_id", lambda service, parent_id, slug: "CFID")

    # _drive_list_folders: CFID -> [raw], RAW -> [cat-a, cat-b]
    def fake_list_folders(service, parent_id):
        if parent_id == "CFID":
            return [{"name": "raw", "id": "RAW"}]
        if parent_id == "RAW":
            return [{"name": "cat-a", "id": "F1"}, {"name": "cat-b", "id": "F2"}]
        return []

    monkeypatch.setattr(dr, "_drive_list_folders", fake_list_folders)

    # _drive_list_pdfs: F1 -> [doc1(10), doc2(20)], F2 -> [doc3(30)]
    def fake_list_pdfs(service, parent_id):
        if parent_id == "F1":
            return [
                {"id": "id1", "name": "doc1.pdf", "mimeType": "application/pdf", "size": "10"},
                {"id": "id2", "name": "doc2.pdf", "mimeType": "application/pdf", "size": "20"},
            ]
        if parent_id == "F2":
            return [
                {"id": "id3", "name": "doc3.pdf", "mimeType": "application/pdf", "size": "30"},
            ]
        return []

    monkeypatch.setattr(dr, "_drive_list_pdfs", fake_list_pdfs)

    # Fake downloader: emette log "download.ok" per doc2 e doc3
    def fake_downloader(
        service,
        remote_root_folder_id,
        local_root_dir,
        *,
        progress,
        context,
        redact_logs,
        chunk_size=8388608,
    ):
        lg = logging.getLogger("pipeline.drive.download")
        lg.propagate = False
        # Scrivi i file come farebbe il downloader reale, poi emetti i log
        p2 = Path(local_root_dir) / "cat-a" / "doc2.pdf"
        p2.parent.mkdir(parents=True, exist_ok=True)
        p2.write_bytes(b"x" * 20)
        lg.info("download.ok", extra={"file_path": str(p2)})

        p3 = Path(local_root_dir) / "cat-b" / "doc3.pdf"
        p3.parent.mkdir(parents=True, exist_ok=True)
        p3.write_bytes(b"x" * 30)
        lg.info("download.ok", extra={"file_path": str(p3)})
        return 2

    monkeypatch.setattr(dr, "download_drive_pdfs_to_local", fake_downloader)

    # Pre-create doc1.pdf to simulate skip
    base_root = tmp_path / "out"
    base_dir = base_root / "timmy-kb-dummy" / "raw" / "cat-a"
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "doc1.pdf").write_bytes(b"x" * 10)

    # Collect progress callbacks
    progress_events = []

    def on_progress(done, total, label):
        progress_events.append((done, total, label))

    written = dr.download_raw_from_drive_with_progress(
        slug="dummy",
        base_root=base_root,
        require_env=True,
        overwrite=False,
        logger=None,
        on_progress=on_progress,
    )

    # Expect: 1 skip (doc1) + 2 download.ok (doc2, doc3)
    assert progress_events == [
        (1, 3, "cat-a/doc1.pdf"),
        (2, 3, "cat-a/doc2.pdf"),
        (3, 3, "cat-b/doc3.pdf"),
    ]
    # And written contains only updated/new (doc2, doc3)
    written_set = {p.as_posix() for p in written}
    assert (base_root / "timmy-kb-dummy" / "raw" / "cat-a" / "doc2.pdf").as_posix() in written_set
    assert (base_root / "timmy-kb-dummy" / "raw" / "cat-b" / "doc3.pdf").as_posix() in written_set
    assert all(p.suffix.lower() == ".pdf" for p in written)


def test_download_with_root_level_pdfs(monkeypatch, tmp_path):
    import ui.services.drive_runner as dr

    class Ctx:
        slug = "dummy"
        redact_logs = False
        env = {"DRIVE_ID": "PARENT"}

    monkeypatch.setattr(dr, "ClientContext", type("_C", (), {"load": staticmethod(lambda **_: Ctx())}))
    monkeypatch.setattr(dr, "get_drive_service", lambda ctx: object())
    monkeypatch.setattr(dr, "_get_existing_client_folder_id", lambda service, parent_id, slug: "CFID")

    def _fake_folders(service, parent_id):
        if parent_id == "CFID":
            return [{"name": "raw", "id": "RAW"}]
        return []

    monkeypatch.setattr(dr, "_drive_list_folders", _fake_folders)
    monkeypatch.setattr(
        dr,
        "_drive_list_pdfs",
        lambda svc, folder_id: [{"id": "id0", "name": "root.pdf", "size": "12"}] if folder_id == "RAW" else [],
    )

    def _fake_downloader(service, remote_root_folder_id, local_root_dir, **kwargs):
        dest = Path(local_root_dir) / "root.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")
        return 1

    monkeypatch.setattr(dr, "download_drive_pdfs_to_local", _fake_downloader)

    captured = []

    def _on_progress(done, total, label):
        captured.append((done, total, label))

    written = dr.download_raw_from_drive_with_progress(
        "dummy", base_root=tmp_path, require_env=False, on_progress=_on_progress
    )

    assert any(path.name == "root.pdf" for path in written)
    assert captured == [(1, 1, "root.pdf")]


def test_plan_raw_download_requires_existing_folder(monkeypatch, tmp_path):
    import ui.services.drive_runner as dr

    class Ctx:
        slug = "dummy"
        redact_logs = False
        env = {"DRIVE_ID": "PARENT"}

    monkeypatch.setattr(dr, "ClientContext", type("_C", (), {"load": staticmethod(lambda **_: Ctx())}))
    monkeypatch.setattr(dr, "get_drive_service", lambda ctx: object())

    def _fake_list_folders(service, parent_id):
        if parent_id == "PARENT":
            return [{"name": "timmy-kb-dummy", "id": "CFID"}]
        if parent_id == "CFID":
            return [{"name": "raw", "id": "RAW"}]
        return []

    def _fake_list_pdfs(service, parent_id):
        if parent_id == "RAW":
            return [{"name": "root.pdf"}]
        return []

    monkeypatch.setattr(dr, "_drive_list_folders", _fake_list_folders)
    monkeypatch.setattr(dr, "_drive_list_pdfs", _fake_list_pdfs)

    conflicts, labels = dr.plan_raw_download("dummy", base_root=tmp_path, require_env=False)

    assert conflicts == []
    assert labels == ["root.pdf"]


def test_plan_raw_download_errors_when_client_folder_missing(monkeypatch, tmp_path):
    import ui.services.drive_runner as dr

    class Ctx:
        slug = "dummy"
        redact_logs = False
        env = {"DRIVE_ID": "PARENT"}

    monkeypatch.setattr(dr, "ClientContext", type("_C", (), {"load": staticmethod(lambda **_: Ctx())}))
    monkeypatch.setattr(dr, "get_drive_service", lambda ctx: object())
    monkeypatch.setattr(dr, "_drive_list_folders", lambda service, parent_id: [])
    monkeypatch.setattr(dr, "_get_existing_client_folder_id", lambda service, parent_id, slug: None)

    with pytest.raises(RuntimeError) as excinfo:
        dr.plan_raw_download("dummy", base_root=tmp_path, require_env=False)

    assert "Cartella cliente non trovata" in str(excinfo.value)
