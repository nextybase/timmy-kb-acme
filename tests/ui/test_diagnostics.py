from __future__ import annotations

import io
import os
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ui.utils import diagnostics as diag


def test_count_files_with_limit_truncates(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    (root / "nested").mkdir(parents=True)
    for idx in range(5):
        (root / f"file{idx}.txt").write_text("x", encoding="utf-8")
    count, truncated = diag.count_files_with_limit(root, limit=3)
    assert count == 3
    assert truncated is True


def test_collect_log_files_skips_outside_and_symlink(tmp_path: Path) -> None:
    base = tmp_path
    logs_dir = base / "logs"
    logs_dir.mkdir()
    safe_file = logs_dir / "safe.log"
    safe_file.write_text("ok", encoding="utf-8")

    outside = tmp_path / "outside.log"
    outside.write_text("no", encoding="utf-8")
    try:
        symlink = logs_dir / "link.log"
        os.symlink(outside, symlink)
    except OSError:
        # Ambienti Windows senza privilegio symlink: ignora
        pass

    files = diag.collect_log_files(base)
    assert files == [safe_file]


def test_tail_log_bytes_prefers_safe_reader(tmp_path: Path) -> None:
    log_file = tmp_path / "log.txt"
    log_file.write_text("abcdef", encoding="utf-8")
    calls: list[Path] = []

    @contextmanager
    def fake_reader(path: Path) -> Iterator[io.BufferedReader]:
        calls.append(path)
        with path.open("rb") as fh:
            yield fh

    tail = diag.tail_log_bytes(log_file, safe_reader=fake_reader, tail_bytes=4)
    assert tail == b"cdef"
    assert calls == [log_file]


def test_build_logs_archive_applies_limits(tmp_path: Path) -> None:
    files = []
    for idx in range(3):
        path = tmp_path / f"log{idx}.txt"
        path.write_text(f"log-{idx}", encoding="utf-8")
        files.append(path)

    @contextmanager
    def reader(path: Path) -> Iterator[io.BufferedReader]:
        with path.open("rb") as fh:
            yield fh

    data = diag.build_logs_archive(
        files,
        slug="demo",
        safe_reader=reader,
        max_files=2,
        max_total_bytes=20,
        chunk_size=4,
    )

    assert data is not None
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = sorted(archive.namelist())
    assert names == ["log0.txt", "log1.txt"]
    assert archive.read("log0.txt") == b"log-0"
    assert archive.read("log1.txt") == b"log-1"


def test_build_logs_archive_returns_none_on_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.log"

    @contextmanager
    def reader(_: Path) -> Iterator[io.BufferedReader]:
        raise RuntimeError("boom")
        yield  # pragma: no cover

    assert diag.build_logs_archive([missing], slug="demo", safe_reader=reader) is None
