# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType


def write_dotenv(base_dir: Path, text: str) -> Path:
    path = base_dir / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def reload_module(module: ModuleType) -> ModuleType:
    return importlib.reload(module)
