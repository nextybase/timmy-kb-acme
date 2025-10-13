from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest


class _ColumnStub:
    def __enter__(self) -> "_ColumnStub":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False


class _StatusStub:
    def update(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state: Dict[str, Any] = {}
        self.button_returns: Dict[str, bool] = {}
        self.success_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.info_messages: list[str] = []
        self.error_messages: list[str] = []

    def subheader(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def markdown(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def html(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def info(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.info_messages.append(message)

    def warning(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.warning_messages.append(message)

    def success(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.success_messages.append(message)

    def error(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.error_messages.append(message)

    def button(self, label: str, *_args: Any, **_kwargs: Any) -> bool:
        return self.button_returns.get(label, False)

    def columns(self, spec: Tuple[int, ...] | int) -> Tuple[_ColumnStub, ...]:
        count = spec if isinstance(spec, int) else len(spec)
        count = max(int(count), 0)
        return tuple(_ColumnStub() for _ in range(count or 1))

    @contextmanager
    def status(self, *_args: Any, **_kwargs: Any) -> _StatusStub:
        yield _StatusStub()

    def stop(self) -> None:
        raise RuntimeError("stop should not be called in tests")


def _load_manage_module(
    monkeypatch: pytest.MonkeyPatch,
    st_stub: _StreamlitStub,
    slug: str,
    has_raw_result: Tuple[bool, str | None],
) -> None:
    monkeypatch.setitem(sys.modules, "streamlit", st_stub)
    import ui.chrome
    import ui.utils.workspace

    monkeypatch.setattr(ui.chrome, "render_chrome_then_require", lambda allow_without_slug: slug)
    monkeypatch.setattr(ui.utils.workspace, "has_raw_pdfs", lambda _slug: has_raw_result)

    sys.modules.pop("ui.pages.manage", None)
    manage = importlib.import_module("ui.pages.manage")
    monkeypatch.setattr(manage, "_render_drive_tree", None, raising=False)
    monkeypatch.setattr(manage, "_render_drive_diff", None, raising=False)


def test_manage_probe_raw_success(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = _StreamlitStub()
    st_stub.button_returns["Rileva PDF in raw/"] = True

    raw_path = str(Path("output") / "timmy-kb-acme" / "raw")
    _load_manage_module(monkeypatch, st_stub, slug="acme", has_raw_result=(True, raw_path))

    assert any("PDF rilevati" in msg for msg in st_stub.success_messages)
    assert not st_stub.warning_messages


def test_manage_probe_raw_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = _StreamlitStub()
    st_stub.button_returns["Rileva PDF in raw/"] = True

    raw_path = str(Path("output") / "timmy-kb-acme" / "raw")
    _load_manage_module(monkeypatch, st_stub, slug="acme", has_raw_result=(False, raw_path))

    assert not st_stub.success_messages
    assert any("Nessun PDF" in msg for msg in st_stub.warning_messages)
