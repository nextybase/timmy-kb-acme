# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ui.types import NavigationLike, StreamlitLike

from .streamlit_stub import StreamlitStub


class _NavStub:
    """Adapter minimo per l'oggetto navigation.run() usato in onboarding."""

    def run(self) -> None:
        return None


class StreamlitStubAdapter(StreamlitLike):
    """
    Adatta tests.ui.StreamlitStub al Protocol StreamlitLike.

    Non cambia il comportamento dei test: deleghe sui metodi usati e no-op sicuri.
    """

    def __init__(self, stub: StreamlitStub) -> None:
        self._stub = stub
        self.session_state = stub.session_state
        self.query_params = stub.query_params

    def set_page_config(
        self,
        *,
        page_title: str,
        page_icon: Any | None = None,
        layout: str = "wide",
        initial_sidebar_state: str = "expanded",
    ) -> None:
        return None

    def columns(self, spec: Sequence[int] | int) -> Sequence[Any]:
        return self._stub.columns(spec)

    def container(self, **_kwargs: Any):
        return self._stub.container()

    def expander(self, label: str, *, expanded: bool = False):
        return self._stub.expander(label, expanded=expanded)

    def status(self, label: str, *, expanded: bool = False, error_label: str | None = None, **_kwargs: Any):
        return self._stub.status(label, expanded=expanded)

    def button(self, label: str, *args: Any, **kwargs: Any) -> bool:
        return self._stub.button(label, *args, **kwargs)

    def checkbox(
        self,
        label: str,
        *,
        value: bool = False,
        help: str | None = None,
        **kwargs: Any,
    ) -> bool:
        return self._stub.checkbox(label, value=value, **kwargs)

    def image(self, image: Any, **kwargs: Any) -> Any:
        return getattr(self._stub, "image", lambda *_a, **_k: None)(image, **kwargs)

    def markdown(self, body: str, **kwargs: Any) -> Any:
        return self._stub.markdown(body, **kwargs)

    def info(self, body: str, **kwargs: Any) -> Any:
        return self._stub.info(body, **kwargs)

    def warning(self, body: str, **kwargs: Any) -> Any:
        return self._stub.warning(body, **kwargs)

    def success(self, body: str, **kwargs: Any) -> Any:
        return self._stub.success(body, **kwargs)

    def error(self, body: str, **kwargs: Any) -> Any:
        return self._stub.error(body, **kwargs)

    def toast(self, body: str, **kwargs: Any) -> Any:
        return self._stub.toast(body, **kwargs)

    def navigation(self, pages: Mapping[str, Sequence[Any]], *, position: str = "top") -> NavigationLike:
        return _NavStub()

    def stop(self) -> None:
        self._stub.stop()

    def rerun(self) -> None:
        self._stub.rerun()

    def title(self, msg: str, **_kwargs: Any) -> None:
        self._stub.info(msg)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stub, name)
