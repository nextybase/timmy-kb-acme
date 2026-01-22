# SPDX-License-Identifier: GPL-3.0-only
"""Helper per funzionalità diagnostiche della UI."""

from __future__ import annotations

import io
import json
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager, Dict, Iterator, List, Optional, Sequence, Tuple, cast

from pipeline.exceptions import ConfigError, PathTraversalError
from pipeline.path_utils import ensure_within_and_resolve, iter_safe_paths, sanitize_filename
from ui.utils.context_cache import get_client_context

SafeReader = Callable[[Path], ContextManager[io.BufferedReader]]

MAX_DIAGNOSTIC_FILES = 2000
TAIL_BYTES = 4000
MAX_LOG_FILES = 50
LOG_CHUNK_SIZE = 64 * 1024
MAX_TOTAL_LOG_BYTES = 5 * 1024 * 1024  # ~5 MiB


def resolve_repo_root_dir(slug: str) -> Optional[Path]:
    """Ritorna la repo_root_dir del client se disponibile, None altrimenti."""
    try:
        ctx = get_client_context(slug, require_env=False)
    except Exception:
        return None
    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        return None
    return Path(repo_root_dir)


def count_files_with_limit(root: Optional[Path], *, limit: int = MAX_DIAGNOSTIC_FILES) -> Tuple[int, bool]:
    """Conta i file sotto root, fermandosi a limit. Ritorna (count, truncated)."""
    if root is None or not root.is_dir():
        return 0, False
    total = 0
    truncated = False

    def _on_skip(_path: Path, _reason: str) -> None:
        # Ignora silenziosamente elementi non accessibili/symlink.
        return

    for _ in iter_safe_paths(root, include_files=True, include_dirs=False, on_skip=_on_skip):
        total += 1
        if total >= limit:
            truncated = True
            break
    if truncated:
        return limit, True
    return total, False


def summarize_workspace_folders(repo_root_dir: Optional[Path]) -> Optional[Dict[str, Tuple[int, bool]]]:
    """Restituisce i conteggi file per cartelle chiave del workspace."""
    if repo_root_dir is None:
        return None
    raw = repo_root_dir / "raw"
    book = repo_root_dir / "book"
    semantic = repo_root_dir / "semantic"
    return {
        "raw": count_files_with_limit(raw),
        "book": count_files_with_limit(book),
        "semantic": count_files_with_limit(semantic),
    }


def build_workspace_summary(
    slug: str,
    log_files: Sequence[Path],
    *,
    repo_root_dir: Optional[Path] = None,
) -> Optional[Dict[str, object]]:
    """Costruisce un riepilogo JSON del workspace (counts + log selezionati)."""
    resolved = repo_root_dir or resolve_repo_root_dir(slug)
    if resolved is None:
        return None
    try:
        counts = summarize_workspace_folders(resolved)
    except Exception:
        counts = None
    safe_names = [sanitize_filename(path.name) for path in log_files if path]
    return {
        "slug": slug,
        "repo_root_dir": str(resolved),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "log_files": safe_names,
    }


def collect_log_files(repo_root_dir: Optional[Path]) -> List[Path]:
    """Restituisce i file log (ordinati per mtime desc) garantendo path-safety."""
    if repo_root_dir is None:
        return []
    try:
        logs_dir = ensure_within_and_resolve(repo_root_dir, repo_root_dir / "logs")
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
        safe_path = ensure_within_and_resolve(path.parent, path)
        size = safe_path.stat().st_size
        offset = max(0, size - tail_bytes)
        if safe_reader:
            with safe_reader(safe_path) as fh:
                fh.seek(offset)
                return fh.read(tail_bytes)
        with _open_binary(safe_path) as fh:
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
    logs_root: Optional[Path] = None
    repo_root_dir = resolve_repo_root_dir(slug)
    workspace_summary = build_workspace_summary(slug, selected, repo_root_dir=repo_root_dir)
    included_logs: list[str] = []
    if repo_root_dir:
        try:
            logs_root = ensure_within_and_resolve(repo_root_dir, repo_root_dir / "logs")
        except (ConfigError, PathTraversalError):
            logs_root = None
    if logs_root is None and selected:
        logs_root = selected[0].resolve().parent
    summary_written = False
    try:
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in selected:
                if written_total >= max_total_bytes:
                    break
                try:
                    safe_path: Optional[Path] = None
                    if logs_root is not None:
                        try:
                            safe_path = ensure_within_and_resolve(logs_root, file_path)
                        except (ConfigError, PathTraversalError):
                            safe_path = None
                    if safe_path is None:
                        safe_path = ensure_within_and_resolve(file_path.parent, file_path)
                    parent_component = sanitize_filename(safe_path.parent.name) if safe_path.parent else ""
                    basename = sanitize_filename(safe_path.name)
                    arc_components = [part for part in (parent_component, basename) if part]
                    arcname = "/".join(arc_components) or basename
                    reader_cm: ContextManager[io.BufferedReader]
                    if safe_reader:
                        reader_cm = safe_reader(safe_path)
                    else:
                        reader_cm = _open_binary(safe_path)
                    with reader_cm as fh:
                        with zf.open(arcname, mode="w") as zout:
                            while written_total < max_total_bytes:
                                chunk = fh.read(min(chunk_size, max_total_bytes - written_total))
                                if not chunk:
                                    break
                                zout.write(chunk)
                                written_total += len(chunk)
                    included_logs.append(basename if basename else safe_path.name)
                except Exception:
                    continue
            if workspace_summary:
                workspace_summary["log_files"] = included_logs
            if workspace_summary and written_total > 0:
                try:
                    payload = json.dumps(workspace_summary, indent=2).encode("utf-8")
                    zf.writestr("workspace_summary.json", payload)
                    summary_written = True
                except Exception:
                    pass
    except Exception:
        return None

    if written_total == 0 and not summary_written:
        return None

    return buffer.getvalue()


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


@contextmanager
def _open_binary(path: Path) -> Iterator[io.BufferedReader]:
    safe_path = ensure_within_and_resolve(path.parent, path)
    with safe_path.open("rb") as fh:
        yield fh
