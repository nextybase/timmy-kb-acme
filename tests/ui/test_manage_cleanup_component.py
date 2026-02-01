# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pytest

from ui.manage import cleanup as cleanup_component


class _ColumnStub:
    def __init__(self, responses: list[bool]) -> None:
        self._responses = responses

    def button(self, _label: str, **_kwargs: Any) -> bool:
        return self._responses.pop(0)


class _StreamlitStub:
    def __init__(self, confirm: bool = True) -> None:
        self.session_state: dict[str, Any] = {}
        self.dialog = None
        self._confirm = confirm
        self.warnings: list[str] = []
        self.info_messages: list[str] = []
        self.rerun_called = False

    def warning(self, message: str, **_kwargs: Any) -> None:
        self.warnings.append(message)

    def info(self, message: str, **_kwargs: Any) -> None:
        self.info_messages.append(message)

    def columns(self, count: int) -> tuple[_ColumnStub, _ColumnStub]:
        if count != 2:  # pragma: no cover - difesa contro regressioni
            raise AssertionError("expected two columns")
        return _ColumnStub([False]), _ColumnStub([self._confirm])

    def button(self, _label: str, **_kwargs: Any) -> bool:
        return False

    def rerun(self) -> None:
        self.rerun_called = True


def test_client_display_name_prefers_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Entry:
        def __init__(self, slug: str, nome: str) -> None:
            self.slug = slug
            self.nome = nome

    def _load() -> Iterable[_Entry]:
        return [_Entry("dummy", "Acme"), _Entry("other", "Other")]

    name = cleanup_component.client_display_name("dummy", _load)
    assert name == "Acme"

    name_unknown = cleanup_component.client_display_name("missing", _load)
    assert name_unknown == "missing"


class _LayoutStub:
    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir


def test_list_raw_subfolders_returns_sorted(tmp_path: Path) -> None:
    root = tmp_path / "output"
    root.mkdir()
    for folder in ("b", "a", "c"):
        (root / folder).mkdir()
    (root / "file.txt").write_text("x", encoding="utf-8")

    layout = _LayoutStub(root)
    folders = cleanup_component.list_raw_subfolders("dummy", layout=layout)
    assert folders == ["a", "b", "c"]


def test_open_cleanup_modal_success(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = _StreamlitStub(confirm=True)
    calls: list[tuple[str, bool]] = []
    slug_updates: list[str] = []

    def _run(slug: str, assume_yes: bool) -> int:
        calls.append((slug, assume_yes))
        return 0

    cleanup_component.open_cleanup_modal(
        st=st_stub,
        slug="dummy",
        client_name="Dummy srl",
        set_slug=slug_updates.append,
        run_cleanup=_run,
        perform_cleanup=None,
    )

    assert calls == [("dummy", True)]
    assert slug_updates == [""]
    result = st_stub.session_state["__cleanup_done"]
    assert result["level"] == "success"
    assert "Dummy" in result["text"]
    assert st_stub.rerun_called is True


def test_open_cleanup_modal_missing_runner_sets_error(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = _StreamlitStub(confirm=True)
    slug_updates: list[str] = []

    monkeypatch.setattr(cleanup_component, "resolve_run_cleanup", lambda: None)

    cleanup_component.open_cleanup_modal(
        st=st_stub,
        slug="dummy",
        client_name="Dummy srl",
        set_slug=slug_updates.append,
        run_cleanup=None,
        perform_cleanup=None,
    )

    assert "__cleanup_done" in st_stub.session_state
    result = st_stub.session_state["__cleanup_done"]
    assert result["level"] == "error"
    assert "non disponibile" in result["text"]
    assert slug_updates == []
    assert st_stub.rerun_called is True
