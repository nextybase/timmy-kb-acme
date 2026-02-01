# SPDX-License-Identifier: GPL-3.0-or-later
import importlib


def test_show_error_with_details_renders_message(monkeypatch):
    module = importlib.reload(importlib.import_module("ui.utils.streamlit_fragments"))

    class _DummyExpander:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class _DummyStreamlit:
        def __init__(self):
            self.errors: list[str] = []
            self.exceptions: list[str] = []

        def error(self, message: str) -> None:
            self.errors.append(message)

        def exception(self, exc: BaseException) -> None:
            self.exceptions.append(str(exc))

        def expander(self, *_args, **_kwargs):
            return _DummyExpander()

    dummy_st = _DummyStreamlit()
    monkeypatch.setattr(module, "st", dummy_st, raising=False)

    class _DummyLogger:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object] | None]] = []

        def exception(self, event: str, *, extra: dict[str, object] | None = None) -> None:
            self.calls.append((event, extra))

    logger = _DummyLogger()

    module.show_error_with_details(
        logger,
        "Operazione non riuscita",
        RuntimeError("boom"),
        event="ui.test.failure",
        extra={"slug": "dummy"},
        show_details=True,
    )

    assert dummy_st.errors == ["Operazione non riuscita"]
    assert dummy_st.exceptions == ["boom"]
    assert logger.calls and logger.calls[0][0] == "ui.test.failure"
    assert logger.calls[0][1] and logger.calls[0][1]["slug"] == "dummy"
