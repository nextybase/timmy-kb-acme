# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import logging
import os
from pathlib import Path

from tests._helpers.workspace_paths import local_workspace_dir

import pytest

from pipeline.exceptions import ConfigError


def _reset_store(tmp_path):
    module = importlib.import_module("ui.clients_store")
    importlib.reload(module)
    module.REPO_ROOT = tmp_path
    module.DB_DIR = Path("clients_db")
    module.DB_FILE = Path("clients.yaml")
    os.environ["CLIENTS_DB_DIR"] = "clients_db"
    os.environ["CLIENTS_DB_FILE"] = "clients.yaml"
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
    assert store._db_file().exists()
    data = store.load_clients()
    assert data == []


def test_clients_db_path_override(tmp_path, monkeypatch):
    module = _reset_store(tmp_path)
    monkeypatch.delenv("CLIENTS_DB_DIR", raising=False)
    monkeypatch.delenv("CLIENTS_DB_FILE", raising=False)
    monkeypatch.setenv("CLIENTS_DB_PATH", "clients_db/alt_db/registry.yaml")
    module.REPO_ROOT = tmp_path
    module.DB_DIR = Path("clients_db")
    module.DB_FILE = Path("clients.yaml")
    module.ensure_db()
    expected_dir = tmp_path / "clients_db" / "alt_db"
    assert module._db_dir() == expected_dir
    assert module._db_file() == expected_dir / "registry.yaml"


def test_clients_db_path_rejects_non_clients_db(tmp_path, monkeypatch):
    module = _reset_store(tmp_path)
    monkeypatch.delenv("CLIENTS_DB_DIR", raising=False)
    monkeypatch.delenv("CLIENTS_DB_FILE", raising=False)
    monkeypatch.setenv("CLIENTS_DB_PATH", "alt_db/registry.yaml")
    module.REPO_ROOT = tmp_path
    module.DB_DIR = Path("clients_db")
    module.DB_FILE = Path("clients.yaml")
    with pytest.raises(ConfigError):
        module.ensure_db()


def test_clients_db_dir_rejects_non_clients_db(tmp_path, monkeypatch):
    module = _reset_store(tmp_path)
    monkeypatch.delenv("CLIENTS_DB_PATH", raising=False)
    monkeypatch.setenv("CLIENTS_DB_DIR", "alt_db")
    monkeypatch.setenv("CLIENTS_DB_FILE", "clients.yaml")
    module.REPO_ROOT = tmp_path
    module.DB_DIR = Path("clients_db")
    module.DB_FILE = Path("clients.yaml")
    with pytest.raises(ConfigError):
        module.ensure_db()


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


def test_upsert_preserves_dummy_flag(store):
    store.ensure_db()
    store.upsert_client(store.ClientEntry(slug="dummy", nome="Dummy", stato="active", dummy=True))
    entries = store.load_clients()
    assert entries[0].slug == "dummy"
    assert entries[0].dummy is True


def test_set_state_updates_existing_only(store):
    store.ensure_db()
    store.upsert_client(store.ClientEntry(slug="gamma", nome="Gamma", stato="nuovo"))
    store.set_state("gamma", "finito")
    entries = store.load_clients()
    assert entries[0].stato == "finito"
    store.set_state("missing", "arricchito")
    entries_after = store.load_clients()
    assert [e.slug for e in entries_after] == ["gamma"]


def test_upsert_rejects_invalid_slug(store):
    store.ensure_db()
    with pytest.raises(ConfigError):
        store.upsert_client(store.ClientEntry(slug="Not Valid", nome="Foo", stato="nuovo"))
    with pytest.raises(ConfigError):
        store.upsert_client(store.ClientEntry(slug="UPPER", nome="Bar", stato="nuovo"))


def test_set_state_rejects_invalid_slug(store):
    store.ensure_db()
    store.upsert_client(store.ClientEntry(slug="delta", nome="Delta", stato="nuovo"))
    with pytest.raises(ConfigError):
        store.set_state("UPPER", "arricchito")
    entries = store.load_clients()
    assert [e.slug for e in entries] == ["delta"]


def test_optional_env_empty_raises(store, monkeypatch):
    monkeypatch.setenv("CLIENTS_DB_DIR", "  ")
    with pytest.raises(ConfigError) as excinfo:
        store._optional_env("CLIENTS_DB_DIR")
    assert excinfo.value.code == "assistant.env.empty"


def test_optional_env_reader_error_raises(store, monkeypatch):
    def _raise_runtime(name: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("ui.clients_store.get_env_var", _raise_runtime)
    with pytest.raises(ConfigError) as excinfo:
        store._optional_env("CLIENTS_DB_DIR")
    assert excinfo.value.code == "assistant.env.read_failed"


@pytest.mark.parametrize(
    "payload",
    (
        "::::",
        "- foo\n",
        "- nome: Foo\n",
    ),
)
def test_parse_entries_rejects_invalid_payloads(store, payload):
    with pytest.raises(ConfigError) as excinfo:
        store._parse_entries(payload)
    assert excinfo.value.code == "clients_store.yaml.invalid"


def test_base_repo_root_ignores_workspace_root_dir(tmp_path, monkeypatch, caplog):
    module = _reset_store(tmp_path)
    workspace_root = local_workspace_dir(tmp_path / "output", "prova")
    monkeypatch.setenv(module.WORKSPACE_ROOT_ENV, workspace_root.as_posix())
    monkeypatch.delenv(module.REPO_ROOT_ENV, raising=False)
    module.REPO_ROOT = tmp_path

    with caplog.at_level(logging.INFO):
        resolved = module._base_repo_root()

    assert resolved == tmp_path
    assert any(rec.getMessage() == "clients_store.workspace_root_ignored" for rec in caplog.records)
