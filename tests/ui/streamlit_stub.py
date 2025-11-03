# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional


class _DialogRunner:
    def __init__(self, fn: Callable[[], None]) -> None:
        self._fn = fn

    def __call__(self) -> None:
        self._fn()


class StreamlitStub:
    def __init__(self) -> None:
        self.session_state: Dict[str, Any] = {}
        self._forms: Dict[str, Callable[..., Any]] = {}
        self._buttons: Dict[str, Iterator[bool]] = {}
        self._columns: deque[List["_Column"]] = deque()
        self._last_toast: Optional[str] = None
        self._rerun_called = False
        self.button_calls: list[str] = []
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.success_messages: list[str] = []
        self.error_messages: list[str] = []
        # Estensioni per test OAuth/UI
        self.query_params: Dict[str, Optional[str]] = {}
        self._stop_exc_cls: type[BaseException] = RuntimeError

    # ---- UI primitives ----
    def button(
        self, label: str, *, key: Optional[str] = None, on_click: Optional[Callable[..., Any]] = None, **kwargs: Any
    ) -> bool:
        key = key or label
        self.button_calls.append(label)
        iterator = self._buttons.get(key)
        if iterator is None:
            return False
        try:
            pressed = next(iterator)
        except StopIteration:
            pressed = False
        if pressed and callable(on_click):
            on_click()
        return pressed

    def register_button_sequence(self, key: str, presses: List[bool]) -> None:
        self._buttons[key] = iter(presses)

    def selectbox(
        self, label: str, options: List[str], index: int = 0, key: Optional[str] = None, **_kwargs: Any
    ) -> str:
        key = key or label
        choice = self.session_state.get(key)
        if choice not in options:
            choice = options[index]
        self.session_state[key] = choice
        return choice

    def radio(self, label: str, options: List[str], index: int = 0, key: Optional[str] = None, **_kwargs: Any) -> str:
        return self.selectbox(label, options, index=index, key=key)

    def text_input(self, label: str, value: str = "", key: Optional[str] = None, **_kwargs: Any) -> str:
        key = key or label
        v = self.session_state.get(key, value)
        self.session_state[key] = v
        return v

    def text_area(self, label: str, value: str = "", key: Optional[str] = None, **_kwargs: Any) -> str:
        return self.text_input(label, value=value, key=key)

    def checkbox(self, label: str, value: bool = False, key: Optional[str] = None, **_kwargs: Any) -> bool:
        key = key or label
        v = bool(self.session_state.get(key, value))
        self.session_state[key] = v
        return v

    def toggle(self, label: str, value: bool = False, key: Optional[str] = None, **kwargs: Any) -> bool:
        return self.checkbox(label, value=value, key=key, **kwargs)

    def number_input(
        self,
        label: str,
        value: float | int = 0,
        key: Optional[str] = None,
        **_kwargs: Any,
    ) -> float | int:
        key = key or label
        v = self.session_state.get(key, value)
        self.session_state[key] = v
        return v

    # ---- Forms ----
    def form(self, name: str, clear_on_submit: bool = False):
        @contextmanager
        def _form_context() -> Iterator[None]:
            yield
            if clear_on_submit:
                self.session_state.clear()

        return _form_context()

    def form_submit_button(self, label: str, **kwargs: Any) -> bool:
        return self.button(label, **kwargs)

    # ---- Dialogs ----
    def dialog(self, title: str, **_kwargs: Any) -> Callable[[Callable[[], None]], _DialogRunner]:
        def _wrap(fn: Callable[[], None]) -> _DialogRunner:
            return _DialogRunner(fn)

        return _wrap

    def file_uploader(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def page_link(self, *args: Any, **_kwargs: Any) -> None:
        return None

    def link_button(self, *args: Any, **_kwargs: Any) -> None:
        return None

    class _Expander:
        def __enter__(self) -> "StreamlitStub._Expander":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def expander(self, *_args: Any, **_kwargs: Any) -> "_Expander":
        return StreamlitStub._Expander()

    def code(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    # ---- Layout ----
    def columns(self, spec: List[int] | int) -> List["_Column"]:
        if isinstance(spec, int):
            spec = [1] * spec
        cols = [_Column(self, idx) for idx, _ in enumerate(spec)]
        self._columns.append(cols)
        return cols

    def container(self, **_kwargs: Any) -> "_Container":
        return _Container(self)

    def status(self, *args: Any, **kwargs: Any) -> "_StatusContext":
        return _StatusContext()

    def spinner(self, *args: Any, **kwargs: Any) -> "_StatusContext":
        return _StatusContext()

    # ---- Feedback ----
    def success(self, msg: str, **_kwargs: Any) -> None:
        self._last_toast = msg
        self.success_messages.append(msg)

    def warning(self, msg: str, **_kwargs: Any) -> None:
        self._last_toast = msg
        self.warning_messages.append(msg)

    def error(self, msg: str, **_kwargs: Any) -> None:
        self._last_toast = msg
        self.error_messages.append(msg)

    def info(self, msg: str, **_kwargs: Any) -> None:
        self._last_toast = msg
        self.info_messages.append(msg)

    def toast(self, msg: str, **_kwargs: Any) -> None:
        self._last_toast = msg

    # ---- Misc ----
    def html(self, _content: str, **_kwargs: Any) -> None:
        return None

    def markdown(self, _content: str, **_kwargs: Any) -> None:
        return None

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def subheader(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def caption(self, _content: str, **_kwargs: Any) -> None:
        return None

    def rerun(self) -> None:
        self._rerun_called = True

    def stop(self) -> None:
        raise self._stop_exc_cls("stop requested")


class _Column:
    def __init__(self, st: StreamlitStub, index: int) -> None:
        self._st = st
        self._index = index

    def __enter__(self) -> "_Column":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return self._st.button(*args, **kwargs)

    def selectbox(self, *args: Any, **kwargs: Any) -> Any:
        return self._st.selectbox(*args, **kwargs)

    def text_input(self, *args: Any, **kwargs: Any) -> Any:
        return self._st.text_input(*args, **kwargs)

    def text_area(self, *args: Any, **kwargs: Any) -> Any:
        return self._st.text_area(*args, **kwargs)


class _Container:
    def __init__(self, st: StreamlitStub) -> None:
        self._st = st

    def __enter__(self) -> "_Container":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return self._st.button(*args, **kwargs)

    def text_input(self, *args: Any, **kwargs: Any) -> Any:
        return self._st.text_input(*args, **kwargs)


class _StatusContext:
    def __enter__(self) -> "_StatusContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def update(self, *args: Any, **kwargs: Any) -> None:
        return None
