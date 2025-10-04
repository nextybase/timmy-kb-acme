from __future__ import annotations

from typing import Callable, Optional, TypeVar, cast

try:
    from streamlit import fragment as _fragment_impl
except Exception:  # pragma: no cover
    _fragment_impl = None

FragmentCallable = Callable[[Callable[[], None]], Callable[[], None]]
_FRAGMENT: Optional[FragmentCallable] = cast(Optional[FragmentCallable], _fragment_impl)

T = TypeVar("T")


def run_fragment(key: str, body: Callable[[], T]) -> T:
    """Execute `body` inside a Streamlit fragment when available and return its result."""
    if _FRAGMENT is not None:
        sentinel = object()
        box: dict[str, object | T] = {"value": sentinel}

        def _wrapped() -> None:
            box["value"] = body()

        safe_key = key.replace("/", "_").replace(".", "_")
        _wrapped.__name__ = f"fragment_{safe_key}"
        _wrapped.__qualname__ = _wrapped.__name__
        runner = _FRAGMENT(_wrapped)
        runner()
        value = box["value"]
        if value is sentinel:  # pragma: no cover - should not happen
            raise RuntimeError("Streamlit fragment did not execute the body")
        return cast(T, value)
    return body()
