# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import timmy_kb.cli.retriever as retriever


def test_retriever_safe_log_alias_smoke() -> None:
    assert callable(retriever._safe_log)  # noqa: SLF001
    retriever._safe_log("info", "retriever.smoke", extra={"x": 1})  # noqa: SLF001
