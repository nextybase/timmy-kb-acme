# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from pipeline.log_viewer import LogFileInfo
from ui.pages import logs_panel as page


class _ColumnFacade:
    def __init__(self, stub: "_StreamlitStub") -> None:
        self._stub = stub

    def __enter__(self) -> "_ColumnFacade":  # pragma: no cover - trivial
        return self

    def __exit__(self, *args: Any) -> None:  # pragma: no cover - trivial
        return None

    def selectbox(self, *args: Any, **kwargs: Any) -> Any:
        return self._stub.selectbox(*args, **kwargs)

    def slider(self, *args: Any, **kwargs: Any) -> Any:
        return self._stub.slider(*args, **kwargs)

    def multiselect(self, *args: Any, **kwargs: Any) -> Any:
        return self._stub.multiselect(*args, **kwargs)

    def text_input(self, *args: Any, **kwargs: Any) -> Any:
        return self._stub.text_input(*args, **kwargs)


class _Expander:
    def __enter__(self) -> None:  # pragma: no cover - trivial
        return None

    def __exit__(self, *args: Any) -> None:  # pragma: no cover - trivial
        return None


class _StreamlitStub:
    def __init__(self) -> None:
        self.subheaders: List[str] = []
        self.captions: List[str] = []
        self.info_messages: List[str] = []
        self.warnings: List[str] = []
        self.codes: List[str] = []
        self.markdowns: List[str] = []
        self.dataframes: List[Any] = []
        self.selectbox_return: Any = None
        self.slider_return: int = 500
        self.multiselect_return: List[str] | None = None
        self.text_input_return: str = ""

    def subheader(self, text: str) -> None:
        self.subheaders.append(text)

    def caption(self, text: str) -> None:
        self.captions.append(text)

    def info(self, message: Any) -> None:
        self.info_messages.append(str(message))

    def code(self, text: str) -> None:
        self.codes.append(text)

    def markdown(self, text: str) -> None:
        self.markdowns.append(text)

    def warning(self, message: Any) -> None:
        self.warnings.append(str(message))

    def expander(self, *_args: Any, **_kwargs: Any) -> _Expander:
        return _Expander()

    def columns(self, spec: List[int]) -> List[_ColumnFacade]:
        return [_ColumnFacade(self) for _ in spec]

    def selectbox(self, *_args: Any, **_kwargs: Any) -> Any:
        return self.selectbox_return

    def slider(self, *_args: Any, **_kwargs: Any) -> int:
        return self.slider_return

    def multiselect(self, *_args: Any, **kwargs: Any) -> List[str]:
        if self.multiselect_return is None:
            default = kwargs.get("default")
            if isinstance(default, list):
                return default
            return []
        return self.multiselect_return

    def text_input(self, *_args: Any, **_kwargs: Any) -> str:
        return self.text_input_return

    def dataframe(self, data: Any) -> None:
        self.dataframes.append(data)


@pytest.fixture()
def streamlit_stub(monkeypatch: pytest.MonkeyPatch) -> _StreamlitStub:
    stub = _StreamlitStub()
    monkeypatch.setattr(page, "st", stub)
    monkeypatch.setattr(page, "render_chrome_then_require", lambda **_k: None)
    return stub


def test_shows_hint_when_no_logs(
    streamlit_stub: _StreamlitStub, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_dir = tmp_path / ".timmy_kb" / "logs"
    monkeypatch.setattr(page, "list_global_log_files", lambda max_files=20: [])
    monkeypatch.setattr(page, "get_global_logs_dir", lambda: log_dir)

    page.main()

    assert streamlit_stub.subheaders == ["Log dashboard"]
    assert streamlit_stub.info_messages
    assert Path(streamlit_stub.codes[0]).resolve() == log_dir.resolve()


def test_data_frame_filtered_by_level(
    streamlit_stub: _StreamlitStub, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_file = LogFileInfo(path=tmp_path / "log.log", size_bytes=10, mtime=0)
    log_dir = tmp_path / ".timmy_kb" / "logs"
    monkeypatch.setattr(page, "list_global_log_files", lambda max_files=20: [fake_file])
    monkeypatch.setattr(page, "get_global_logs_dir", lambda: log_dir)

    rows: List[Dict[str, Any]] = [
        {"level": "INFO", "event": "ok"},
        {"level": "ERROR", "event": "bad"},
    ]
    streamlit_stub.selectbox_return = fake_file
    streamlit_stub.multiselect_return = ["ERROR"]
    monkeypatch.setattr(page, "load_log_sample", lambda path, max_lines=500: rows)

    page.main()

    assert streamlit_stub.dataframes
    filtered = streamlit_stub.dataframes[-1]
    assert isinstance(filtered, list)
    assert filtered == [{"level": "ERROR", "event": "bad"}]
