# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Mapping, MutableMapping, Protocol, Sequence


class NavigationLike(Protocol):
    """Interfaccia minimale per l'oggetto restituito da st.navigation(...)."""

    def run(self) -> None: ...


class StreamlitLike(Protocol):
    """
    Boundary tipizzato tra core e Streamlit.

    È intenzionalmente minimale e modellato sui punti di contatto usati
    in onboarding_ui.py (preflight, routing, feedback utente).
    """

    session_state: MutableMapping[str, Any]
    query_params: MutableMapping[str, Any]

    def set_page_config(
        self,
        *,
        page_title: str,
        page_icon: Any | None = ...,
        layout: str = ...,
        initial_sidebar_state: str = ...,
    ) -> None: ...

    def columns(self, spec: Sequence[int] | int) -> Sequence[Any]: ...

    def container(self, **kwargs: Any) -> AbstractContextManager[Any]: ...

    def expander(self, label: str, *, expanded: bool = ...) -> AbstractContextManager[Any]: ...

    def status(
        self, label: str, *, expanded: bool = ..., error_label: str | None = ..., **kwargs: Any
    ) -> AbstractContextManager[Any]: ...

    def button(self, label: str, *args: Any, **kwargs: Any) -> bool: ...

    def checkbox(
        self,
        label: str,
        *,
        value: bool = ...,
        help: str | None = ...,
        **kwargs: Any,
    ) -> bool: ...

    def image(self, image: Any, **kwargs: Any) -> Any: ...

    def markdown(self, body: str, **kwargs: Any) -> Any: ...

    def info(self, body: str, **kwargs: Any) -> Any: ...

    def warning(self, body: str, **kwargs: Any) -> Any: ...

    def success(self, body: str, **kwargs: Any) -> Any: ...

    def error(self, body: str, **kwargs: Any) -> Any: ...

    def toast(self, body: str, **kwargs: Any) -> Any: ...

    def navigation(self, pages: Mapping[str, Sequence[Any]], *, position: str = ...) -> NavigationLike: ...

    def stop(self) -> None: ...

    def rerun(self) -> None: ...
