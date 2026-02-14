# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, NoReturn

from pipeline.exceptions import RetrieverError


def _apply_error_context(exc: RetrieverError, *, code: str, **extra: Any) -> RetrieverError:
    if getattr(exc, "code", None) is None:
        setattr(exc, "code", code)
    for key, value in extra.items():
        if value is not None and not hasattr(exc, key):
            setattr(exc, key, value)
    return exc


def _raise_retriever_error(message: str, *, code: str, **extra: Any) -> NoReturn:
    err = RetrieverError(message)
    _apply_error_context(err, code=code, **extra)
    raise err
