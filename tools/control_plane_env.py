# SPDX-License-Identifier: GPL-3.0-or-later
# tools/control_plane_env.py
"""
Helper per confinare la modalità control-plane (tooling/admin) in modo deterministico.

Principio:
- UI Runtime: sempre TIMMY_BETA_STRICT=1 (enforced nell'entrypoint UI).
- Tooling/Admin: può operare in non-strict, ma deve essere esplicito e isolato.

Nota: i tools girano già in subprocess rispetto alla UI, ma questo helper rende
il comportamento ripetibile e documentabile (e riduce branching entropico).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Mapping, MutableMapping, Optional


@contextmanager
def control_plane_env(
    *,
    env: MutableMapping[str, str] | None = None,
    force_non_strict: bool = True,
) -> Iterator[Mapping[str, str]]:
    """
    Context manager che forza TIMMY_BETA_STRICT=0 (se richiesto) e ripristina a fine blocco.
    """
    target = env if env is not None else os.environ
    prev = target.get("TIMMY_BETA_STRICT")
    try:
        if force_non_strict:
            target["TIMMY_BETA_STRICT"] = "0"
        yield target
    finally:
        if prev is None:
            target.pop("TIMMY_BETA_STRICT", None)
        else:
            target["TIMMY_BETA_STRICT"] = prev


__all__ = ["control_plane_env"]
