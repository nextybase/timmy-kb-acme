# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Dict, Optional

from ui.utils.streamlit_baseline import require_streamlit_feature
from ui.utils.stubs import get_streamlit


def enrich_log_extra(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extra: Dict[str, Any] = {} if base is None else dict(base)
    st = get_streamlit()
    user_obj = getattr(st, "user", None)
    user_email = getattr(user_obj, "email", None)
    if user_email:
        extra.setdefault("user", user_email)
    return extra


def show_success(message: str) -> None:
    st = get_streamlit()
    toast_fn = require_streamlit_feature(st, "toast")
    toast_fn(message)
