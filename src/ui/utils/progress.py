# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/progress.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional, TypeVar

from pipeline.logging_utils import get_structured_logger
from ui.utils.streamlit_baseline import require_streamlit_feature
from ui.utils.stubs import get_streamlit

logger = get_structured_logger("ui.progress")
T = TypeVar("T")


@dataclass(slots=True)
class ProgressReporter:
    label: str
    _bar: Optional[object] = None
    _disabled: bool = False
    _warned: bool = False

    def start(self) -> None:
        st = get_streamlit()
        progress_fn = require_streamlit_feature(st, "progress")
        self._bar = progress_fn(0, text=self.label)

    def update(self, value: float, *, text: Optional[str] = None) -> None:
        if self._bar is None or self._disabled:
            return
        try:
            if text is None:
                self._bar.progress(value)  # type: ignore[union-attr]
            else:
                self._bar.progress(value, text=text)  # type: ignore[union-attr]
        except (ValueError, TypeError, RuntimeError) as exc:
            if not self._warned:
                logger.warning(
                    "ui.progress.update_failed",
                    extra={
                        "label": self.label,
                        "value": value,
                        "text": text,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                self._warned = True
            self._disabled = True


def run_with_progress(items: Iterable[T], *, label: str, on_each: Callable[[T], None]) -> None:
    """Esegue `on_each` su ogni item mostrando progress e mantenendo compatibilita' API."""
    items_list = list(items)
    total = max(len(items_list), 1)
    reporter = ProgressReporter(label=label)
    reporter.start()
    for idx, item in enumerate(items_list, start=1):
        on_each(item)
        reporter.update(min(idx, total) / total, text=f"{label} ({idx}/{total})")
    reporter.update(1.0, text=f"{label} (completato)")
