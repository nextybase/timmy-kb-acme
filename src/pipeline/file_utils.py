# src/pipeline/file_utils.py
"""
File utilities: scritture atomiche e path-safety per la pipeline Timmy-KB.

Obiettivi:
- Offrire write testuali/bytes sicure, atomiche e robuste a interruzioni.
- Prevenire path traversal con guardie semplici e riutilizzabili.
- Centralizzare la logica di fsync best-effort (evita file troncati).

API principali:
- ensure_within(base: Path, target: Path) -> None
- safe_write_text(path: Path, data: str, *, encoding="utf-8", atomic=True) -> None
- safe_write_bytes(path: Path, data: bytes, *, atomic=True) -> None

Note:
- `atomic=True` esegue la scrittura su file temporaneo + `os.replace()` atomico.
- Viene creata la directory padre se assente (mkdir(parents=True, exist_ok=True)).
- `fsync` è best-effort: si prova a sincronizzare sia il file che la directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from .exceptions import ConfigError
from .logging_utils import get_structured_logger

_logger = get_structured_logger("pipeline.file_utils")


def ensure_within(base: Path, target: Path) -> None:
    """
    Garantisce che `target` risieda sotto `base` una volta risolti i path.
    Solleva ConfigError in caso contrario.

    Args:
        base: directory radice consentita.
        target: path del file da validare.
    """
    try:
        base_r = Path(base).resolve()
        tgt_r = Path(target).resolve()
    except Exception as e:
        raise ConfigError(f"Impossibile risolvere i path: {e}", file_path=str(target)) from e

    try:
        # Fallisce con ValueError se tgt_r non è sotto base_r (gestisce anche prefissi simili)
        tgt_r.relative_to(base_r)
    except Exception:
        raise ConfigError(
            f"Path traversal rilevato: {tgt_r} non è sotto {base_r}",
            file_path=str(target),
        )


def _fsync_best_effort(fd: int, path: Optional[Path] = None) -> None:
    """Sincronizza il file descriptor in modo best-effort."""
    try:
        os.fsync(fd)
    except Exception:
        # Non alziamo: preferiamo non interrompere la pipeline per limiti FS
        _logger.debug("fsync(file) best-effort fallito", extra={"file_path": str(path) if path else None})


def _fsync_dir_best_effort(dir_path: Path) -> None:
    """Sincronizza la directory contenitore in modo best-effort."""
    try:
        # Su Windows O_DIRECTORY non esiste; il blocco è già best-effort.
        dfd = os.open(str(dir_path), os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except Exception:
        _logger.debug("fsync(dir) best-effort fallito", extra={"dir_path": str(dir_path)})


def safe_write_text(path: Path, data: str, *, encoding: str = "utf-8", atomic: bool = True) -> None:
    """
    Scrive testo su file in modo sicuro.
    - Se `atomic=True`, scrive su file temporaneo e poi sostituisce atomically con `os.replace`.
    - Crea le directory padre se mancano.
    - Esegue fsync best-effort sul file e sulla directory.

    Solleva:
        ConfigError: su errori di I/O bloccanti (es. directory non scrivibile).
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
                _fsync_best_effort(f.fileno(), path)
            _fsync_dir_best_effort(path.parent)
            return
        except Exception as e:
            raise ConfigError(f"Scrittura file fallita: {e}", file_path=str(path)) from e

    # Modalità atomica: temp + replace
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
            _fsync_best_effort(tmp.fileno(), tmp_path)
        os.replace(str(tmp_path), str(path))  # atomic move
        _fsync_dir_best_effort(path.parent)
    except Exception as e:
        # Proviamo a rimuovere il temp se esiste
        try:
            if "tmp_path" in locals() and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise ConfigError(f"Scrittura atomica fallita: {e}", file_path=str(path)) from e


def safe_write_bytes(path: Path, data: bytes, *, atomic: bool = True) -> None:
    """
    Scrive bytes su file in modo sicuro (stesse garanzie di safe_write_text).
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ConfigError(f"Impossibile creare la directory padre: {e}", file_path=str(path)) from e

    if not atomic:
        try:
            with open(path, "wb") as f:
                f.write(data)
                _fsync_best_effort(f.fileno(), path)
            _fsync_dir_best_effort(path.parent)
            return
        except Exception as e:
            raise ConfigError(f"Scrittura file (bytes) fallita: {e}", file_path=str(path)) from e

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=str(path.parent),
            prefix=".tmp-",
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(data)
            _fsync_best_effort(tmp.fileno(), tmp_path)
        os.replace(str(tmp_path), str(path))
        _fsync_dir_best_effort(path.parent)
    except Exception as e:
        try:
            if "tmp_path" in locals() and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise ConfigError(f"Scrittura atomica (bytes) fallita: {e}", file_path=str(path)) from e


__all__ = [
    "ensure_within",
    "safe_write_text",
    "safe_write_bytes",
]
