"""Helper per funzionalità diagnostiche della UI."""

from __future__ import annotations

import io
import os
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, ContextManager, Dict, List, Optional, Sequence, Tuple, cast

from pipeline.exceptions import ConfigError, PathTraversalError
from pipeline.path_utils import ensure_within_and_resolve

SafeReader = Callable[[Path], ContextManager[io.BufferedReader]]

MAX_DIAGNOSTIC_FILES = 2000
TAIL_BYTES = 4000
MAX_LOG_FILES = 50
LOG_CHUNK_SIZE = 64 * 1024
MAX_TOTAL_LOG_BYTES = 5 * 1024 * 1024  # ~5 MiB


def resolve_base_dir(slug: str) -> Optional[Path]:
    """Ritorna la base_dir del client se disponibile, None altrimenti."""
    try:
        from pipeline.context import ClientContext
    except Exception:
        return None
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    except Exception:
        return None
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        return None
    return Path(base_dir)


def count_files_with_limit(root: Optional[Path], *, limit: int = MAX_DIAGNOSTIC_FILES) -> Tuple[int, bool]:
    """Conta i file sotto root, fermandosi a limit. Ritorna (count, truncated)."""
    if root is None or not root.is_dir():
        return 0, False
    total = 0
    for _dirpath, _dirnames, filenames in os.walk(root):
        total += len(filenames)
        if total >= limit:
            return limit, True
    return total, False


def summarize_workspace_folders(base_dir: Optional[Path]) -> Optional[Dict[str, Tuple[int, bool]]]:
    """Restituisce i conteggi file per cartelle chiave del workspace."""
    if base_dir is None:
        return None
    raw = base_dir / "raw"
    book = base_dir / "book"
    semantic = base_dir / "semantic"
    return {
        "raw": count_files_with_limit(raw),
        "book": count_files_with_limit(book),
        "semantic": count_files_with_limit(semantic),
    }


def collect_log_files(base_dir: Optional[Path]) -> List[Path]:
    """Restituisce i file log (ordinati per mtime desc) garantendo path-safety."""
    if base_dir is None:
        return []
    try:
        logs_dir = ensure_within_and_resolve(base_dir, base_dir / "logs")
    except (ConfigError, PathTraversalError):
        return []
    if not logs_dir.exists() or not logs_dir.is_dir():
        return []

    safe_files: List[Path] = []
    try:
        for entry in logs_dir.iterdir():
            if entry.is_symlink():
                continue
            try:
                resolved = ensure_within_and_resolve(logs_dir, entry)
            except (ConfigError, PathTraversalError):
                continue
            if resolved.is_file():
                safe_files.append(resolved)
    except Exception:
        return []

    safe_files.sort(key=_safe_mtime, reverse=True)
    return safe_files


def get_safe_reader() -> Optional[SafeReader]:
    """Ritorna il reader sicuro se disponibile (pipeline optional)."""
    try:
        from pipeline.file_utils import open_for_read_bytes_selfguard
    except Exception:
        return None

    def _reader(path: Path) -> ContextManager[io.BufferedReader]:
        return cast(ContextManager[io.BufferedReader], open_for_read_bytes_selfguard(path))

    return _reader


def tail_log_bytes(
    path: Path,
    *,
    safe_reader: Optional[SafeReader],
    tail_bytes: int = TAIL_BYTES,
) -> Optional[bytes]:
    """Ritorna gli ultimi tail_bytes del file, usando il reader sicuro se possibile."""
    try:
        size = path.stat().st_size
        offset = max(0, size - tail_bytes)
        if safe_reader:
            with safe_reader(path) as fh:
                fh.seek(offset)
                return fh.read(tail_bytes)
        with path.open("rb") as fh:
            fh.seek(offset)
            return fh.read(tail_bytes)
    except Exception:
        return None


def build_logs_archive(
    files: Sequence[Path],
    *,
    slug: str,
    safe_reader: Optional[SafeReader],
    max_files: int = MAX_LOG_FILES,
    chunk_size: int = LOG_CHUNK_SIZE,
    max_total_bytes: int = MAX_TOTAL_LOG_BYTES,
) -> Optional[bytes]:
    """Crea un archivio zip con i log selezionati rispettando i limiti indicati."""
    if not files:
        return None

    selected = list(files[:max_files])
    written_total = 0
    buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in selected:
                if written_total >= max_total_bytes:
                    break
                try:
                    with zf.open(file_path.name, mode="w") as zout:
                        reader_cm: ContextManager[io.BufferedReader]
                        if safe_reader:
                            reader_cm = safe_reader(file_path)
                        else:
                            reader_cm = _open_binary(file_path)
                        with reader_cm as fh:
                            while written_total < max_total_bytes:
                                chunk = fh.read(min(chunk_size, max_total_bytes - written_total))
                                if not chunk:
                                    break
                                zout.write(chunk)
                                written_total += len(chunk)
                except Exception:
                    continue
    except Exception:
        return None

    if written_total == 0:
        return None

    return buffer.getvalue()


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


@contextmanager
def _open_binary(path: Path) -> ContextManager[io.BufferedReader]:
    with path.open("rb") as fh:
        yield fh
