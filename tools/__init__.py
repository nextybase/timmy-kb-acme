# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pkgutil
from pathlib import Path

# Estende il path del package per includere anche src/tools (dove vivono i moduli Python).
__path__ = pkgutil.extend_path(__path__, __name__)  # type: ignore[assignment]
_src_tools = Path(__file__).resolve().parents[1] / "src" / "tools"
if _src_tools.exists():
    __path__.append(str(_src_tools))  # type: ignore[attr-defined]
