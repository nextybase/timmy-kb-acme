from pathlib import Path


def test_download_with_progress_adapter(monkeypatch, tmp_path):
    import logging
    import src.config_ui.drive_runner as dr

    # Fake ClientContext
    class Ctx:
        slug = "foo"
        redact_logs = False
        env = {"DRIVE_ID": "PARENT"}

    monkeypatch.setattr(dr, "ClientContext", type("_C", (), {"load": staticmethod(lambda **_: Ctx())}))

    # Fake Drive service and helpers
    class Svc:
        pass

    monkeypatch.setattr(dr, "get_drive_service", lambda ctx: Svc())
    monkeypatch.setattr(dr, "create_drive_folder", lambda svc, name, parent_id, redact_logs=False: "CFID")

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
    def fake_downloader(service, remote_root_folder_id, local_root_dir, *, progress, context, redact_logs, chunk_size=8388608):
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
    base_dir = base_root / "timmy-kb-foo" / "raw" / "cat-a"
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "doc1.pdf").write_bytes(b"x" * 10)

    # Collect progress callbacks
    progress_events = []

    def on_progress(done, total, label):
        progress_events.append((done, total, label))

    written = dr.download_raw_from_drive_with_progress(
        slug="foo",
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
    assert (base_root / "timmy-kb-foo" / "raw" / "cat-a" / "doc2.pdf").as_posix() in written_set
    assert (base_root / "timmy-kb-foo" / "raw" / "cat-b" / "doc3.pdf").as_posix() in written_set
    assert all(p.suffix.lower() == ".pdf" for p in written)
