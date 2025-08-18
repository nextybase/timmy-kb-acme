# src/pipeline/logging_utils.py
"""
Utility per la creazione di logger strutturati per la pipeline Timmy-KB.

Caratteristiche:
- Formattazione uniforme per console e file (opzionalmente con rotazione).
- Campo contestuale `slug` (se disponibile) in ogni record di log.
- Supporto opzionale a `run_id` (correlazione di una singola esecuzione).
- Possibilità di iniettare campi extra di base (`extra_base`) su ogni record.
- Comportamento “safe”: nessun crash se il file di log non è scrivibile
  (degrada a console-only con avviso).

Note architetturali:
- Nessun I/O non necessario oltre alla creazione opzionale del file di log.
- Nessuna dipendenza dai moduli di orchestrazione; può essere usato ovunque.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union, Protocol, runtime_checkable, Dict, Any
from logging.handlers import RotatingFileHandler


@runtime_checkable
class SupportsSlug(Protocol):
    """Protocol di typing per oggetti che espongono l'attributo `slug`."""
    slug: str


def _make_context_filter(
    context: Optional[SupportsSlug],
    run_id: Optional[str],
    extra_base: Optional[Dict[str, Any]],
):
    """Crea un filtro che arricchisce ogni record con slug/run_id/extra_base."""
    def _filter(record: logging.LogRecord) -> bool:
        # slug
        if context is not None:
            try:
                setattr(record, "slug", getattr(context, "slug", "n/a"))
            except Exception:
                setattr(record, "slug", "n/a")
        # run_id
        if run_id is not None:
            try:
                setattr(record, "run_id", run_id)
            except Exception:
                pass
        # extra_base
        if extra_base:
            for k, v in extra_base.items():
                # non sovrascrivere se già presente
                if not hasattr(record, k):
                    try:
                        setattr(record, k, v)
                    except Exception:
                        pass
        return True
    return _filter


def get_structured_logger(
    name: str = "default",
    log_file: Optional[Union[str, Path]] = None,
    level: Optional[int] = None,
    rotate: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    context: Optional[SupportsSlug] = None,
    *,
    run_id: Optional[str] = None,
    extra_base: Optional[Dict[str, Any]] = None,
) -> logging.Logger:
    """
    Crea un logger strutturato con supporto per console e file, opzionalmente
    legato a un contesto che espone `.slug` (es. `ClientContext`).

    Args:
        name: Nome del logger (namespace).
        log_file: Percorso del file di log; se `None` scrive solo su console.
        level: Livello di logging (default: `logging.INFO`).
        rotate: Se `True`, abilita `RotatingFileHandler` per il file di log.
        max_bytes: Dimensione massima del file prima della rotazione.
        backup_count: Numero massimo di file di backup per la rotazione.
        context: Oggetto opzionale con attributo `.slug` da riportare nei record.
        run_id: Identificativo opzionale per correlare i log di una singola esecuzione.
        extra_base: Dizionario di campi extra da iniettare in ogni record (non stampati
                    se non inclusi nel formatter).

    Returns:
        logging.Logger: Logger configurato e pronto all'uso.

    Raises:
        Nessuna eccezione viene propagata per errori sul file di log: in tal caso
        il logger degrada a console-only e registra un `warning`.

    Side Effects:
        - Se `log_file` è indicato, crea la cartella padre e il file (se possibile).
        - Azzera gli handler esistenti sul logger nominato per evitare duplicazioni.
    """
    logger = logging.getLogger(name)

    # Evita handler duplicati (design decision: logger "pulito" per coerenza output)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Livello di default
    if level is None:
        level = logging.INFO
    logger.setLevel(level)

    # Importante: non propagare al root logger per evitare doppie emissioni
    logger.propagate = False

    # Formatter uniforme; include slug/run_id solo se forniti
    fmt = "%(asctime)s | %(levelname)s | %(name)s"
    if context is not None:
        fmt += " | slug=%(slug)s"
    if run_id is not None:
        fmt += " | run_id=%(run_id)s"
    fmt += " | %(message)s"

    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # Filtro che arricchisce i record
    ctx_filter = _make_context_filter(context, run_id, extra_base)

    # Handler console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.addFilter(ctx_filter)
    logger.addHandler(ch)

    # Handler file, se richiesto
    if log_file:
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if rotate:
                fh = RotatingFileHandler(
                    log_file_path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
            else:
                fh = logging.FileHandler(log_file_path, encoding="utf-8")
            fh.setFormatter(formatter)
            fh.addFilter(ctx_filter)
            logger.addHandler(fh)
        except Exception as e:
            # Se il file non è creabile, degrada elegantemente a console-only
            logger.warning(f"Impossibile creare file di log {log_file_path}: {e}. Logging solo su console.")

    return logger


__all__ = ["get_structured_logger", "SupportsSlug"]
