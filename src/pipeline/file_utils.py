# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/file_utils.py
"""
File utilities: scritture atomiche e path-safety per la pipeline Timmy-KB.

Obiettivi:
- Offrire write testuali/bytes sicure, atomiche e robuste a interruzioni.
- Centralizzare la logica di fsync con errori deterministici quando richiesto.
- Non imporre policy di perimetro: la guardia STRONG dei path resta in
  `pipeline.path_utils.ensure_within` (SSoT) e va chiamata dai *callers* prima di scrivere.

Indice (ruolo funzioni):
- `_fsync_file(fd, *, path=None)`: sincronizza il file descriptor in modo deterministico.
- `_fsync_dir(dir_path)`: sincronizza la directory padre in modo deterministico.
- `safe_write_text(path, data, *, encoding="utf-8", atomic=True, fsync=False)`:
  scrittura **testo** sicura.
  - Crea le directory mancanti.
  - `atomic=True`: usa temp file + `os.replace()` atomico. Con `fsync=True` fa flush+fsync.
  - `atomic=False`: scrive direttamente e puo fare fsync sul file.
  - Esegue `fsync` della directory padre solo se `fsync=True`.
- `safe_write_bytes(path, data, *, atomic=True, fsync=False)`: come sopra, per **bytes**.

Note:
- Nessun fsync implicito quando `fsync=False`; tutti gli fsync sono deterministici e falliscono fast.
- Questo modulo non valida che `path` sia "dentro" un perimetro: quel controllo va fatto a monte.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from .exceptions import ConfigError
from .logging_utils import get_structured_logger
from .path_utils import (
    ensure_within_and_resolve,
    refresh_iter_safe_pdfs_cache_for_path,
    strip_extended_length_path,
    to_extended_length_path,
)

_logger = get_structured_logger("pipeline.file_utils")


def _post_write_hooks(path: Path) -> None:
    """Hook post-scrittura per mantenere coerenza cache/path utilities.

    In strict mode (default) non effettua il prewarm della cache per evitare dipendenze da clock.
    In non-strict (dev/tooling/dummy) il prewarm resta attivo per UX.
    """
    if Path(path).suffix.lower() != ".pdf":
        return

    from .beta_flags import is_beta_strict

    prewarm = not is_beta_strict()
    refresh_iter_safe_pdfs_cache_for_path(Path(path), prewarm=prewarm)


def _fsync_file(fd: int, *, path: Optional[Path] = None) -> None:
    """Sincronizza il file descriptor e fallisce fast se l'operazione non riesce."""
    try:
        os.fsync(fd)
    except Exception as exc:  # pragma: no cover - dipende da l'FS
        raise ConfigError("fsync(file) fallito.", file_path=str(path) if path else None) from exc


def _fsync_dir(dir_path: Path) -> None:
    """Sincronizza la directory contenitore e fallisce fast se l'operazione non riesce."""
    try:
        flags = getattr(os, "O_DIRECTORY", 0)
        dir_str = to_extended_length_path(dir_path)
        dfd = os.open(dir_str, flags)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except Exception as exc:  # pragma: no cover - dipende da l'OS/FS
        raise ConfigError("fsync(dir) fallito.", file_path=str(dir_path)) from exc


def _extended_str(path: Path) -> str:
    return to_extended_length_path(path) if os.name == "nt" else str(path)


def _resolve_within_base(base: Path, candidate: Path) -> Path:
    if os.name == "nt":
        guard_base = Path(to_extended_length_path(base))
        guard_candidate = Path(to_extended_length_path(candidate))
        resolved = ensure_within_and_resolve(guard_base, guard_candidate)
        return strip_extended_length_path(resolved)
    return ensure_within_and_resolve(base, candidate)


def _best_effort_cleanup(event: str, *, extra: dict[str, object] | None = None) -> None:
    """Cleanup best-effort, ma osservabile (no silent degradation)."""
    try:
        _logger.debug(event, extra=extra or {})
    except Exception:
        # Se anche il logger fallisce, non possiamo fare molto: ma qui siamo in cleanup non critico.
        return


def create_lock_file(path: Path, *, payload: str = "", mode: int = 0o600) -> None:
    """Crea un lock file esclusivo scrivendo opzionalmente un payload."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise ConfigError("Impossibile creare la directory padre del lock.", file_path=str(path)) from exc

    lock_str = _extended_str(path)
    try:
        fd = os.open(lock_str, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    except FileExistsError:
        raise
    except OSError as exc:
        raise ConfigError("Impossibile creare il lock file.", file_path=str(path)) from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            if payload:
                handle.write(payload)
    except Exception as exc:
        raise ConfigError("Scrittura lock file fallita.", file_path=str(path)) from exc


def remove_lock_file(path: Path) -> None:
    """Rimuove il lock file se presente."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as exc:
        raise ConfigError("Impossibile rimuovere il lock file.", file_path=str(path)) from exc


def safe_write_text(
    path: Path,
    data: str,
    *,
    encoding: str = "utf-8",
    atomic: bool = True,
    fsync: bool = False,
) -> None:
    """Scrive testo su file in modo sicuro.

    - Con `atomic=True` scrive su file temporaneo e poi sostituisce con `os.replace`.
    - Crea la directory padre se mancante.
    - Con `fsync=True` fa `flush()` + `fsync()` sul file (temp o diretto).
    - Esegue `fsync` della directory padre solo se `fsync=True`.

    Solleva:
        ConfigError: su errori di I/O bloccanti (es. dir non scrivibile, fsync strict fallito).
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ConfigError("Impossibile creare la directory padre.", file_path=str(path)) from e

    parent_path = path.parent
    path_str = _extended_str(path)
    parent_str = _extended_str(parent_path)

    if not atomic:
        try:
            with open(path_str, "w", encoding=encoding, newline="") as f:
                f.write(data)
                if fsync:
                    f.flush()
                    _fsync_file(f.fileno(), path=path)
            if fsync:
                _fsync_dir(parent_path)
            _post_write_hooks(path)
            return
        except Exception as e:
            raise ConfigError("Scrittura file fallita.", file_path=str(path)) from e

    # Modalita atomica: temp + replace
    tmp_path: Optional[Path] = None
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            delete=False,
            dir=parent_str,
            prefix=".tmp-",
            newline="",
        ) as tmp:
            tmp_name = tmp.name
            tmp_path = Path(tmp_name)
            tmp.write(data)
            if fsync:
                tmp.flush()
                _fsync_file(tmp.fileno(), path=strip_extended_length_path(tmp_name))

        os.replace(tmp_name, path_str)  # atomic move
        if fsync:
            _fsync_dir(parent_path)
        _post_write_hooks(path)
    except Exception as e:
        # Cleanup best-effort, ma osservabile
        if tmp_path is not None:
            try:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                _best_effort_cleanup(
                    "file_utils.tmp_cleanup_failed",
                    extra={
                        "tmp_path": str(tmp_path),
                        "target_path": str(path),
                        "error": repr(cleanup_exc),
                    },
                )
        raise ConfigError("Scrittura atomica fallita.", file_path=str(path)) from e


def safe_write_bytes(
    path: Path,
    data: bytes,
    *,
    atomic: bool = True,
    fsync: bool = False,
) -> None:
    """Scrive bytes su file in modo sicuro (stesse garanzie di `safe_write_text`)."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ConfigError("Impossibile creare la directory padre.", file_path=str(path)) from e

    parent_path = path.parent
    path_str = _extended_str(path)
    parent_str = _extended_str(parent_path)

    if not atomic:
        try:
            with open(path_str, "wb") as f:
                f.write(data)
                if fsync:
                    f.flush()
                    _fsync_file(f.fileno(), path=path)
            if fsync:
                _fsync_dir(parent_path)
            _post_write_hooks(path)
            return
        except Exception as e:
            raise ConfigError("Scrittura file (bytes) fallita.", file_path=str(path)) from e

    tmp_path: Optional[Path] = None
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=parent_str,
            prefix=".tmp-",
        ) as tmp:
            tmp_name = tmp.name
            tmp_path = Path(tmp_name)
            tmp.write(data)
            if fsync:
                tmp.flush()
                _fsync_file(tmp.fileno(), path=strip_extended_length_path(tmp_name))

        os.replace(tmp_name, path_str)
        if fsync:
            _fsync_dir(parent_path)
        _post_write_hooks(path)
    except Exception as e:
        if tmp_path is not None:
            try:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                _best_effort_cleanup(
                    "file_utils.tmp_cleanup_failed",
                    extra={
                        "tmp_path": str(tmp_path),
                        "target_path": str(path),
                        "error": repr(cleanup_exc),
                    },
                )
        raise ConfigError("Scrittura atomica (bytes) fallita.", file_path=str(path)) from e


def safe_append_text(
    root_dir: Path,
    target: Path,
    data: str,
    *,
    encoding: str = "utf-8",
    lock_timeout: float = 5.0,
    fsync: bool = False,
) -> None:
    """Appende testo in modo sicuro usando path-safety, lock file e append diretto.

    Nota: su Windows puo emergere PermissionError durante create/unlink concorrenti
    del lock file. Lo trattiamo come contesa del lock (al pari di FileExistsError),
    con piccoli retry fino a lock_timeout.

    - Con `fsync=True` sincronizza file e directory in modo deterministico.
    """
    root_dir = Path(root_dir)
    resolved_base = root_dir.resolve()
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = resolved_base / candidate

    resolved = _resolve_within_base(resolved_base, candidate)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    parent_path = resolved.parent
    resolved_str = _extended_str(resolved)
    lock_path = resolved.parent / f"{resolved.name}.lock"
    lock_path_str = _extended_str(lock_path)

    deadline = time.monotonic() + max(lock_timeout, 0.0)
    lock_fd: Optional[int] = None

    while True:
        try:
            lock_fd = os.open(lock_path_str, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except (FileExistsError, PermissionError):
            if time.monotonic() > deadline:
                raise ConfigError(
                    "Timeout nell'acquisire il lock per l'append.",
                    file_path=str(resolved),
                )
            time.sleep(0.05)
            continue
        except OSError as exc:
            raise ConfigError(
                "Impossibile creare il lock file.",
                file_path=str(resolved),
            ) from exc

    try:
        try:
            with open(resolved_str, "a", encoding=encoding, newline="") as f:
                f.write(data)
                if fsync:
                    f.flush()
                    _fsync_file(f.fileno(), path=resolved)
            if fsync:
                _fsync_dir(parent_path)
        except Exception as exc:
            raise ConfigError(
                "Append fallito.",
                file_path=str(resolved),
            ) from exc
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except Exception as exc:
                _best_effort_cleanup(
                    "file_utils.lock_close_failed",
                    extra={"lock_path": str(lock_path), "error": repr(exc)},
                )
        try:
            Path(lock_path_str).unlink(missing_ok=True)
        except Exception as exc:
            _logger.warning(
                "file_utils.lock_remove_failed",
                extra={"lock_path": str(lock_path), "reason": str(exc)},
            )
