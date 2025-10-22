from __future__ import annotations

import importlib
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.ui.streamlit_stub import StreamlitStub
from tests.ui.test_manage_probe_raw import register_streamlit_runtime


@contextmanager
def _null_context() -> Iterator[Any]:
    class _Ctx:
        def update(self, *args: Any, **kwargs: Any) -> None:
            return None

    yield _Ctx()


def test_mirror_repo_config_preserves_client_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StreamlitStub()
    stub.container = lambda *_args, **_kwargs: _null_context()
    stub.spinner = lambda *_args, **_kwargs: _null_context()
    stub.register_button_sequence("Genera workspace locale", [False])
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    register_streamlit_runtime(monkeypatch, stub)
    sys.modules.pop("ui.pages.new_client", None)
    new_client = importlib.import_module("ui.pages.new_client")

    slug = "acme"
    template_root = tmp_path
    (template_root / "config").mkdir(parents=True, exist_ok=True)
    (template_root / "config" / "config.yaml").write_text("client_name: Template\nfoo: bar\n", encoding="utf-8")
    client_cfg_dir = template_root / "output" / f"timmy-kb-{slug}" / "config"
    client_cfg_dir.mkdir(parents=True, exist_ok=True)
    (client_cfg_dir / "config.yaml").write_text("client_name: ACME\n", encoding="utf-8")

    monkeypatch.setattr(new_client, "_repo_root", lambda: template_root)

    original = (client_cfg_dir / "config.yaml").read_text(encoding="utf-8")

    new_client._mirror_repo_config_into_client(slug, pdf_bytes=b"pdf")

    updated = (client_cfg_dir / "config.yaml").read_text(encoding="utf-8")
    assert "client_name: ACME" in updated
    assert updated.count("client_name") == original.count("client_name")
    assert "foo: bar" in updated


def test_sanitize_openai_env_removes_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    import ui.pages.new_client as new_client

    stub = StreamlitStub()
    monkeypatch.setattr(new_client, "st", stub, raising=False)
    monkeypatch.setenv("OPENAI_FORCE_HTTPX", "1")

    removed = new_client._sanitize_openai_env()

    assert "OPENAI_FORCE_HTTPX" in removed
    assert os.getenv("OPENAI_FORCE_HTTPX") is None
    assert any("OPENAI_FORCE_HTTPX" in msg for msg in stub.warning_messages)
