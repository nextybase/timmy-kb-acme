# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


def enrich_log_extra(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extra: Dict[str, Any] = {} if base is None else dict(base)
    user_obj = getattr(st, "user", None)
    user_email = getattr(user_obj, "email", None)
    if user_email:
        extra.setdefault("user", user_email)
    return extra


def show_success(message: str) -> None:
    if st is None:
        return
    # TODO(Beta1.0): enforce Streamlit toast() availability and remove fallback.
    toast_fn = getattr(st, "toast", None)
    if callable(toast_fn):
        try:
            toast_fn(message)
            return
        except Exception:
            pass
    st.success(message)
