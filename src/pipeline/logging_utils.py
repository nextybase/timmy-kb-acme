# src/pipeline/logging_utils.py
"""
Utility per la creazione di logger strutturati per la pipeline Timmy-KB.

Caratteristiche:
- Formattazione uniforme per console e file (opzionalmente con rotazione).
- Campo contestuale `slug` (se disponibile) in ogni record di log.
- Comportamento “safe”: nessun crash se il file di log non è scrivibile
  (degrada a console-only con avviso).

Note architetturali:
- Nessun I/O non necessario oltre alla creazione opzionale del file di log.
- Nessuna dipendenza dai moduli di orchestrazione; può essere usato ovunque.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union, Protocol, runtime_checkable
from logging.handlers import RotatingFileHandler


@runtime_checkable
class SupportsSlug(Protocol):
    """Protocol di typing per oggetti che espongono l'attributo `slug`."""
    slug: str


def get_structured_logger(
    name: str = "default",
    log_file: Optional[Union[str, Path]] = None,
    level: Optional[int] = None,
    rotate: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    context: Optional[SupportsSlug] = None,
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

    # Formatter uniforme; include slug solo se è presente un contesto
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s"
        + (" | slug=%(slug)s" if context else "")
        + " | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    if context:
        # Filtro che arricchisce il record con `slug`; torna sempre True per non bloccare il log.
        ch.addFilter(lambda record: setattr(record, "slug", getattr(context, "slug", "n/a")) or True)
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
            if context:
                fh.addFilter(lambda record: setattr(record, "slug", getattr(context, "slug", "n/a")) or True)
            logger.addHandler(fh)
        except Exception as e:
            # Se il file non è creabile, degrada elegantemente a console-only
            logger.warning(f"Impossibile creare file di log {log_file_path}: {e}. Logging solo su console.")

    return logger
