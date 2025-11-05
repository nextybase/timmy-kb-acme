# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/manage/compat.py
from __future__ import annotations

from typing import Any, Optional, cast

from pipeline.path_utils import read_text_safe as _core_read_text_safe
from storage.tags_store import import_tags_yaml_to_db as _core_import_tags_yaml_to_db
from ui.utils.core import safe_write_text as _core_safe_write_text


def safe_write_text(*args: Any, **kwargs: Any) -> None:
    """Wrapper legacy per test che delega alle utility SSoT."""
    _core_safe_write_text(*args, **kwargs)


def read_text_safe(*args: Any, **kwargs: Any) -> Optional[str]:
    """Wrapper legacy per test che delega alle utility SSoT."""
    return cast(Optional[str], _core_read_text_safe(*args, **kwargs))


def import_tags_yaml_to_db(*args: Any, **kwargs: Any) -> None:
    """Wrapper legacy per test che delega allo storage ufficiale."""
    _core_import_tags_yaml_to_db(*args, **kwargs)
