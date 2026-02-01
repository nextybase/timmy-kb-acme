# SPDX-License-Identifier: GPL-3.0-or-later
'"""Grep gate per escludere fallback/placeholder nelle funzioni SSoT."""\n'
from __future__ import annotations

import re
from pathlib import Path


def test_no_shim_return_patterns() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    path_utils = repo_root / "src" / "pipeline" / "path_utils.py"
    content = path_utils.read_text()

    assert re.search(r"except:\s*return\s*\"-\"", content) is None, "Shim '-' rilevato in path_utils"
    assert re.search(r"except:\s*return\s*default", content) is None, "Shim 'default' rilevato in path_utils"
