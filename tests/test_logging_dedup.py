# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
import uuid

from pipeline.logging_utils import get_structured_logger


def test_child_logger_skips_console_when_parent_has_handler(tmp_path, monkeypatch) -> None:
    root_logger = logging.getLogger()
    saved_handlers = list(root_logger.handlers)
    root_logger.handlers = []
    try:
        monkeypatch.setenv("TIMMY_LOG_PROPAGATE", "1")
        parent_name = f"ui.test_dedup_{uuid.uuid4().hex}"
        child_name = f"{parent_name}.child"
        get_structured_logger(parent_name, log_file=tmp_path / "ui.log", propagate=True)
        child = get_structured_logger(child_name, propagate=True)
        console_handlers = [
            h for h in child.handlers if getattr(h, "_logging_utils_key", "").endswith("::console")
        ]
        assert len(console_handlers) <= 1
    finally:
        root_logger.handlers = saved_handlers
