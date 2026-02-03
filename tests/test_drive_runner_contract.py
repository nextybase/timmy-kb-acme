# SPDX-License-Identifier: GPL-3.0-only
import types

import pytest

from ui.services import drive_runner as dr


class DummyCtx:
    def __init__(self, slug: str):
        self.slug = slug
        self.redact_logs = False
        self.env = {"DRIVE_ID": "drive-root"}


class DummyLogger:
    def info(self, *_, **__):
        pass

    def error(self, *_, **__):
        pass


class FakeFiles:
    def __init__(self):
        self.updated = []
        self.created = []

    def update(self, *args, **kwargs):
        file_id = kwargs.get("fileId")
        self.updated.append(file_id)
        return types.SimpleNamespace(execute=lambda: {"id": file_id or "updated"})

    def create(self, *_, **kwargs):
        new_id = f"created-{len(self.created)}"
        self.created.append(new_id)
        return types.SimpleNamespace(execute=lambda: {"id": new_id})


class FakeService:
    def __init__(self):
        self.files_obj = FakeFiles()

    def files(self):
        return self.files_obj


@pytest.fixture(autouse=True)
def silent_logger(monkeypatch):
    monkeypatch.setattr(dr, "_get_logger", lambda *_: DummyLogger())


def test_load_workspace_drive_folders_spec():
    folders = dr._load_workspace_drive_folders()
    assert set(folders) >= {"raw", "config"}


def test_require_semantic_mapping_raises(monkeypatch, tmp_path):
    layout = types.SimpleNamespace(mapping_path=tmp_path / "semantic_mapping.yaml", slug="acme")
    monkeypatch.setattr(dr, "_require_layout_from_context", lambda ctx: layout)
    with pytest.raises(RuntimeError, match="semantic/semantic_mapping\\.yaml"):
        dr._require_semantic_mapping(DummyCtx("acme"))


def test_require_drive_env_raises(monkeypatch):
    ctx = DummyCtx("slug")
    ctx.env = {}
    with pytest.raises(RuntimeError, match="Drive environment incompleto"):
        dr._require_drive_env(ctx)


def test_ensure_client_root_folder_creates(monkeypatch):
    created = []

    def list_folders(_, __):
        return []

    def create_folder(_, name, parent_id, *, redact_logs=False):
        created.append((name, parent_id))
        return f"{name}-id"

    monkeypatch.setattr(dr, "_drive_list_folders", list_folders)
    monkeypatch.setattr(dr, "create_drive_folder", create_folder)
    ctx = DummyCtx("acme")
    folder_id = dr._ensure_client_root_folder(None, parent_id="root", slug="acme", ctx=ctx)
    assert folder_id == "timmy-kb-acme-id"
    assert created == [("timmy-kb-acme", "root")]

    def list_folders_conflict(_, __):
        return [{"name": "timmy-kb-acme", "id": "one"}, {"name": "timmy-kb-acme", "id": "two"}]

    monkeypatch.setattr(dr, "_drive_list_folders", list_folders_conflict)
    with pytest.raises(RuntimeError, match="Troppi root Drive per slug"):
        dr._ensure_client_root_folder(None, parent_id="root", slug="acme", ctx=ctx)


def test_ensure_category_folders_creates(monkeypatch):
    entries = [{"name": "foo", "id": "foo-id"}]

    def list_folders(_, __):
        return list(entries)

    def create_folder(_, name, parent_id, *, redact_logs=False):
        new_id = f"{name}-id"
        entries.append({"name": name, "id": new_id})
        return new_id

    monkeypatch.setattr(dr, "_drive_list_folders", list_folders)
    monkeypatch.setattr(dr, "create_drive_folder", create_folder)
    ctx = DummyCtx("acme")
    result = dr._ensure_category_folders(None, raw_folder_id="raw", category_names=["foo", "bar"], ctx=ctx)
    assert result["foo"] == "foo-id"
    assert result["bar"] == "bar-id"
    assert "bar" in {entry["name"] for entry in entries}

    entries.append({"name": "conflict", "id": "c1"})
    entries.append({"name": "conflict", "id": "c2"})
    with pytest.raises(RuntimeError, match="Più cartelle Drive 'conflict'"):
        dr._ensure_category_folders(None, raw_folder_id="raw", category_names=["conflict"], ctx=ctx)


def test_drive_upload_or_update_bytes_idempotent(monkeypatch):
    monkeypatch.setattr(dr, "_drive_find_child_by_name", lambda *_: [{"id": "existing"}])
    service = FakeService()
    ctx = DummyCtx("acme")
    file_id = dr._drive_upload_or_update_bytes(
        service, "raw", "README.pdf", b"bytes", "application/pdf", ctx=ctx, category="foo"
    )
    assert file_id == "existing"
    assert service.files_obj.updated == ["existing"]

    monkeypatch.setattr(dr, "_drive_find_child_by_name", lambda *_: [])
    file_id = dr._drive_upload_or_update_bytes(
        service, "raw", "README.pdf", b"bytes", "application/pdf", ctx=ctx, category="foo"
    )
    assert file_id.startswith("created-")

    monkeypatch.setattr(dr, "_drive_find_child_by_name", lambda *_: [{"id": "a"}, {"id": "b"}])
    with pytest.raises(RuntimeError, match="Più README"):
        dr._drive_upload_or_update_bytes(
            service, "raw", "README.pdf", b"bytes", "application/pdf", ctx=ctx, category="foo"
        )


def test_emit_readmes_missing_mapping(monkeypatch):
    monkeypatch.setattr(
        dr, "_require_semantic_mapping", lambda ctx: (_ for _ in ()).throw(RuntimeError("semantic missing"))
    )
    monkeypatch.setattr(dr, "_require_drive_env", lambda ctx: None)
    monkeypatch.setattr(dr, "get_client_context", lambda slug, require_drive_env: DummyCtx(slug))
    monkeypatch.setattr(dr, "get_drive_service", lambda ctx: None)
    with pytest.raises(RuntimeError, match="semantic missing"):
        dr.emit_readmes_for_raw("acme", base_root=".", require_env=True)


def test_emit_readmes_missing_drive_env(monkeypatch):
    monkeypatch.setattr(dr, "_require_semantic_mapping", lambda ctx: None)
    monkeypatch.setattr(dr, "_require_drive_env", lambda ctx: (_ for _ in ()).throw(RuntimeError("drive env")))
    monkeypatch.setattr(dr, "get_client_context", lambda slug, require_drive_env: DummyCtx(slug))
    monkeypatch.setattr(dr, "get_drive_service", lambda ctx: None)
    with pytest.raises(RuntimeError, match="drive env"):
        dr.emit_readmes_for_raw("acme", base_root=".", require_env=True)
