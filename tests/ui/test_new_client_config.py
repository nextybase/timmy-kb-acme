# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
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

    slug = "dummy"
    template_root = tmp_path
    (template_root / "config").mkdir(parents=True, exist_ok=True)
    (template_root / "config" / "config.yaml").write_text("client_name: Template\nfoo: bar\n", encoding="utf-8")
    client_cfg_dir = template_root / "output" / f"timmy-kb-{slug}" / "config"
    client_cfg_dir.mkdir(parents=True, exist_ok=True)
    (client_cfg_dir / "config.yaml").write_text("client_name: dummy\n", encoding="utf-8")

    monkeypatch.setattr(new_client, "get_repo_root", lambda: template_root)

    original = (client_cfg_dir / "config.yaml").read_text(encoding="utf-8")

    new_client._mirror_repo_config_into_client(slug, pdf_bytes=b"pdf")

    updated = (client_cfg_dir / "config.yaml").read_text(encoding="utf-8")
    assert "client_name: dummy" in updated
    assert updated.count("client_name") == original.count("client_name")
    assert "foo: bar" in updated


def test_mirror_repo_config_logs_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    stub = StreamlitStub()
    stub.container = lambda *_args, **_kwargs: _null_context()
    stub.spinner = lambda *_args, **_kwargs: _null_context()
    stub.register_button_sequence("Genera workspace locale", [False])
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    register_streamlit_runtime(monkeypatch, stub)
    sys.modules.pop("ui.pages.new_client", None)
    new_client = importlib.import_module("ui.pages.new_client")

    slug = "dummy"
    template_root = tmp_path
    (template_root / "config").mkdir(parents=True, exist_ok=True)
    (template_root / "config" / "config.yaml").write_text("client_name: Template\n", encoding="utf-8")
    client_cfg_dir = template_root / "output" / f"timmy-kb-{slug}" / "config"
    client_cfg_dir.mkdir(parents=True, exist_ok=True)
    (client_cfg_dir / "config.yaml").write_text("client_name: dummy\n", encoding="utf-8")

    monkeypatch.setattr(new_client, "get_repo_root", lambda: template_root)

    class _LoggerStub:
        def __init__(self) -> None:
            self.records: list[tuple[str, dict[str, Any]]] = []

        def warning(self, msg: str, *, extra: dict[str, Any]) -> None:
            self.records.append((msg, extra))

    logger_stub = _LoggerStub()
    monkeypatch.setattr(new_client, "LOGGER", logger_stub, raising=False)

    diagnostics: list[tuple[str, str, str, dict[str, Any]]] = []
    monkeypatch.setattr(
        new_client,
        "_log_diagnostics",
        lambda slug, level, message, *, extra: diagnostics.append((slug, level, message, extra)),
        raising=False,
    )

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("merge failed")

    monkeypatch.setattr(new_client, "deep_merge_dict", _boom, raising=False)

    new_client._mirror_repo_config_into_client(slug)

    assert logger_stub.records, "expected warning log on merge failure"
    msg, extra = logger_stub.records[0]
    assert msg == "ui.new_client.config_merge_failed"
    assert extra["slug"] == slug
    assert extra["dst"].endswith("config.yaml")

    assert diagnostics
    d_slug, level, diag_msg, diag_extra = diagnostics[0]
    assert d_slug == slug
    assert level == "warning"
    assert diag_msg == "ui.new_client.config_merge_failed"
    assert diag_extra["dst"].endswith("config.yaml")
