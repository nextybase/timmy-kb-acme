from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import timmykb.ui.utils.slug as slug_utils


@pytest.fixture(autouse=True)
def _stub_streamlit(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = SimpleNamespace(session_state={})

    def _info(*_args, **_kwargs):
        return None

    def _stop(*_args, **_kwargs):
        raise RuntimeError("stop should not be called in tests")

    stub.info = _info
    stub.stop = _stop
    monkeypatch.setattr(slug_utils, "st", stub, raising=False)
    monkeypatch.setattr(slug_utils, "_qp_set", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(slug_utils, "_qp_get", lambda *_a, **_k: None, raising=False)


def test_persist_active_slug_atomic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture):
    persist_path = tmp_path / "state" / "ui_state.json"
    monkeypatch.setattr(slug_utils, "_PERSIST_PATH", persist_path, raising=False)

    with caplog.at_level(logging.INFO):
        slug_utils.set_active_slug(" ACME ", persist=True, update_query=False)

    saved = json.loads(persist_path.read_text(encoding="utf-8"))
    assert saved == {"active_slug": "acme"}
    assert any(record.getMessage() == "ui.slug.persisted" for record in caplog.records)

    slug_utils.set_active_slug("acme", persist=True, update_query=False)
    saved_again = json.loads(persist_path.read_text(encoding="utf-8"))
    assert saved_again == {"active_slug": "acme"}


def test_save_persisted_uses_safe_utils(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    persist_path = tmp_path / "state" / "ui_state.json"
    monkeypatch.setattr(slug_utils, "_PERSIST_PATH", persist_path, raising=False)

    calls: dict[str, object] = {}

    def fake_ensure(base: Path, target: Path) -> Path:
        calls["ensure"] = (base, target)
        return target

    def fake_safe(path: Path, payload: str, *, encoding: str, atomic: bool) -> None:
        calls["safe"] = {"path": path, "payload": payload, "encoding": encoding, "atomic": atomic}

    monkeypatch.setattr(slug_utils, "ensure_within_and_resolve", fake_ensure, raising=False)
    monkeypatch.setattr(slug_utils, "safe_write_text", fake_safe, raising=False)

    slug_utils._save_persisted("demo")

    base_dir = persist_path.parent
    assert base_dir.exists(), "La directory di persistenza deve essere creata"
    assert calls.get("ensure") == (base_dir, persist_path)

    safe_call = calls.get("safe")
    assert safe_call is not None
    assert safe_call["path"] == persist_path
    assert safe_call["encoding"] == "utf-8"
    assert safe_call["atomic"] is True
    assert json.loads(str(safe_call["payload"]).strip()) == {"active_slug": "demo"}
