# src/pipeline/file_utils.py
"""
File utilities: scritture atomiche e path-safety per la pipeline Timmy-KB.

Obiettivi:
- Offrire write testuali/bytes sicure, atomiche e robuste a interruzioni.
- Centralizzare la logica di fsync (best-effort di default; opzionale più “forte”).
- Non imporre policy di perimetro: la guardia STRONG dei path resta in
  `pipeline.path_utils.ensure_within` (SSoT) e va chiamata dai *callers* prima di scrivere.

Indice (ruolo funzioni):
- `_fsync_file(fd, *, path=None, strict=False)`: sincronizza il file descriptor.
  - `strict=True` → solleva `ConfigError`; altrimenti logga in debug (best-effort).
- `_fsync_dir_best_effort(dir_path)`: tenta la sincronizzazione della directory padre.
  - Non solleva eccezioni (compatibile con Windows/FS remoti).
- `safe_write_text(path, data, *, encoding="utf-8", atomic=True, fsync=False)`:
  scrittura **testo** sicura.
  - Crea le directory mancanti.
  - `atomic=True`: usa temp file + `os.replace()` atomico. Con `fsync=True` fa flush+fsync.
  - `atomic=False`: scrive direttamente e può fare fsync sul file.
  - Sempre prova a fsync-are la directory (best-effort).
- `safe_write_bytes(path, data, *, atomic=True, fsync=False)`: come sopra, per **bytes**.

Note:
- Di default eseguiamo un fsync “soft” (best-effort) anche quando `fsync=False`.
- Questo modulo non valida che `path` sia “dentro” un perimetro: quel controllo va fatto a monte.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from .exceptions import ConfigError
from .logging_utils import get_structured_logger

_logger = get_structured_logger("pipeline.file_utils")


def _fsync_file(fd: int, *, path: Optional[Path] = None, strict: bool = False) -> None:
    """Sincronizza il file descriptor.

    Se `strict=True`, su errore solleva `ConfigError`. Altrimenti logga e continua
    (best-effort).
    """
    try:
        os.fsync(fd)
    except Exception as e:  # pragma: no cover - dipende dall'FS
        if strict:
            raise ConfigError(f"fsync(file) fallito: {e}", file_path=str(path) if path else None) from e
        _logger.debug(
            "fsync(file) best-effort fallito",
            extra={"file_path": str(path) if path else None},
        )


def _fsync_dir_best_effort(dir_path: Path) -> None:
    """Sincronizza la directory contenitore in modo best-effort.

    Su Windows o FS remoti potrebbe non essere disponibile: non solleva.
    """
    try:
        flags = getattr(os, "O_DIRECTORY", 0)
        dfd = os.open(str(dir_path), flags)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except Exception:  # pragma: no cover - dipende dall'OS/FS
        _logger.debug("fsync(dir) best-effort fallito", extra={"dir_path": str(dir_path)})


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
    - Esegue sempre `fsync` della directory padre in best-effort.

    Solleva:
        ConfigError: su errori di I/O bloccanti (es. dir non scrivibile, fsync strict fallito).
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ConfigError(f"Impossibile creare la directory padre: {e}", file_path=str(path)) from e

    if not atomic:
        try:
            with open(path, "w", encoding=encoding, newline="") as f:
                f.write(data)
                if fsync:
                    try:
                        f.flush()
                    except Exception:
                        # flush best-effort: eventuali errori emergeranno in fsync strict
                        pass
                    _fsync_file(f.fileno(), path=path, strict=True)
                else:
                    _fsync_file(f.fileno(), path=path, strict=False)
            _fsync_dir_best_effort(path.parent)
            return
        except Exception as e:
            raise ConfigError(f"Scrittura file fallita: {e}", file_path=str(path)) from e

    # Modalità atomica: temp + replace
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            delete=False,
            dir=str(path.parent),
            prefix=".tmp-",
            newline="",
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(data)
            if fsync:
                try:
                    tmp.flush()
                except Exception:
                    # flush best-effort; fsync strict intercetterà eventuali errori
                    pass
                _fsync_file(tmp.fileno(), path=tmp_path, strict=True)
            else:
                _fsync_file(tmp.fileno(), path=tmp_path, strict=False)

        os.replace(str(tmp_path), str(path))  # atomic move
        _fsync_dir_best_effort(path.parent)
    except Exception as e:
        # Proviamo a rimuovere il temp se esiste
        try:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise ConfigError(f"Scrittura atomica fallita: {e}", file_path=str(path)) from e


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
        raise ConfigError(f"Impossibile creare la directory padre: {e}", file_path=str(path)) from e

    if not atomic:
        try:
            with open(path, "wb") as f:
                f.write(data)
                if fsync:
                    _fsync_file(f.fileno(), path=path, strict=True)
                else:
                    _fsync_file(f.fileno(), path=path, strict=False)
            _fsync_dir_best_effort(path.parent)
            return
        except Exception as e:
            raise ConfigError(f"Scrittura file (bytes) fallita: {e}", file_path=str(path)) from e

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=str(path.parent),
            prefix=".tmp-",
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(data)
            if fsync:
                _fsync_file(tmp.fileno(), path=tmp_path, strict=True)
            else:
                _fsync_file(tmp.fileno(), path=tmp_path, strict=False)

        os.replace(str(tmp_path), str(path))
        _fsync_dir_best_effort(path.parent)
    except Exception as e:
        try:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise ConfigError(f"Scrittura atomica (bytes) fallita: {e}", file_path=str(path)) from e


__all__ = [
    "safe_write_text",
    "safe_write_bytes",
]
