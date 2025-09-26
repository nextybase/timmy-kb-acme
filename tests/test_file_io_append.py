from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path

import pytest

from pipeline import file_utils
from pipeline.exceptions import ConfigError

# Nota: i test seguono una simulazione best-effort; non abbiamo crash reali di processo ma
# verifichiamo che l'utility resti robusta in scenari di concorrenza e errori controllati.


def test_safe_append_text_concurrent_threads(tmp_path: Path) -> None:
    base = tmp_path / "ws"
    base.mkdir()
    target = base / "logs" / "audit.log"

    thread_count = 6
    append_per_thread = 20
    expected_tokens = [f"{tid}-{i}" for tid in range(thread_count) for i in range(append_per_thread)]
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker(tid: int) -> None:
        for i in range(append_per_thread):
            token = f"{tid}-{i}\n"
            try:
                file_utils.safe_append_text(base, target, token)
            except Exception as exc:  # pragma: no cover - solo per debugging test
                with lock:
                    errors.append(exc)

    threads = [threading.Thread(target=worker, args=(tid,), daemon=True) for tid in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    content = target.read_text(encoding="utf-8")
    assert not errors, f"errori in thread: {errors}"
    assert content.endswith("\n"), "Il file deve terminare con newline per evitare record troncati"

    observed_tokens = content.rstrip("\n").split("\n") if content else []
    assert Counter(observed_tokens) == Counter(expected_tokens)


def test_safe_append_text_failure_leaves_file_intact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "ws"
    base.mkdir()
    target = base / "logs" / "audit.log"

    file_utils.safe_append_text(base, target, "seed\n")
    original = target.read_text(encoding="utf-8")

    original_safe_write = file_utils.safe_write_text

    def flaky_safe_write(
        path: Path,
        data: str,
        *,
        encoding: str = "utf-8",
        atomic: bool = True,
        fsync: bool = False,
    ) -> None:
        raise ConfigError("simulated failure", file_path=str(path))

    monkeypatch.setattr(file_utils, "safe_write_text", flaky_safe_write)

    with pytest.raises(ConfigError):
        file_utils.safe_append_text(base, target, "second\n", lock_timeout=0.1)

    assert target.read_text(encoding="utf-8") == original
    lock_path = target.parent / f"{target.name}.lock"
    assert not lock_path.exists()

    monkeypatch.setattr(file_utils, "safe_write_text", original_safe_write)
    file_utils.safe_append_text(base, target, "tail\n")
    assert target.read_text(encoding="utf-8") == original + "tail\n"
