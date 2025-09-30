import importlib

import pytest


def _reset_store(tmp_path):
    module = importlib.import_module("ui.clients_store")
    importlib.reload(module)
    module.REPO_ROOT = tmp_path
    module.DB_DIR = tmp_path / "clients_db"
    module.DB_FILE = module.DB_DIR / "clients.yaml"
    return module


@pytest.fixture()
def store(tmp_path, monkeypatch):
    module = _reset_store(tmp_path)
    monkeypatch.setattr("ui.clients_store.REPO_ROOT", tmp_path)
    monkeypatch.setattr("ui.clients_store.DB_DIR", module.DB_DIR)
    monkeypatch.setattr("ui.clients_store.DB_FILE", module.DB_FILE)
    return module


def test_ensure_db_creates_empty_yaml(store):
    store.ensure_db()
    assert store.DB_FILE.exists()
    data = store.load_clients()
    assert data == []


def test_upsert_preserves_order_and_deduplicates(store):
    store.ensure_db()
    store.upsert_client(store.ClientEntry(slug="alpha", nome="Alpha", stato="nuovo"))
    store.upsert_client(store.ClientEntry(slug="beta", nome="Beta", stato="pronto"))
    store.upsert_client(store.ClientEntry(slug="alpha", nome="Alpha 2", stato="arricchito"))
    store.upsert_client(store.ClientEntry(slug="alpha", nome="Alpha 3", stato="finito"))
    entries = store.load_clients()
    assert [e.slug for e in entries] == ["alpha", "beta"]
    assert entries[0].nome == "Alpha 3"
    assert entries[0].stato == "finito"


def test_set_state_updates_existing_only(store):
    store.ensure_db()
    store.upsert_client(store.ClientEntry(slug="gamma", nome="Gamma", stato="nuovo"))
    store.set_state("gamma", "finito")
    entries = store.load_clients()
    assert entries[0].stato == "finito"
    store.set_state("missing", "arricchito")
    entries_after = store.load_clients()
    assert [e.slug for e in entries_after] == ["gamma"]
