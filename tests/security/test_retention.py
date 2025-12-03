# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
import time
from pathlib import Path

from security.retention import purge_old_artifacts


def test_purge_old_artifacts_removes_old_snapshot(tmp_path: Path) -> None:
    base_dir = tmp_path / "output" / "timmy-kb-dummy"
    target_dir = base_dir / "semantic"
    target_dir.mkdir(parents=True, exist_ok=True)

    old_file = target_dir / "vision.snapshot.txt"
    recent_file = target_dir / "recent.snapshot.txt"
    old_file.write_text("old", encoding="utf-8")
    recent_file.write_text("recent", encoding="utf-8")

    old_timestamp = time.time() - (60 * 60 * 24 * 10)  # 10 giorni fa
    os.utime(old_file, (old_timestamp, old_timestamp))

    removed = purge_old_artifacts(base_dir, days=7)

    assert removed == 1
    assert not old_file.exists()
    assert recent_file.exists()


def test_purge_old_artifacts_handles_missing_base(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert purge_old_artifacts(missing, days=7) == 0
