# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Dict, List

from tools.dummy import orchestrator


def test_readme_counts_with_drive_entries() -> None:
    local_readmes: List[Dict[str, str]] = []
    drive_readmes = {"a": {"path": "drive/a"}, "b": {"path": "drive/b"}, "c": {"path": "drive/c"}}

    local_count, drive_count, total = orchestrator._readme_counts(local_readmes, drive_readmes)

    assert local_count == 0
    assert drive_count == 3
    assert total == 3
