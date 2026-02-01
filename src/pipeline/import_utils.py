# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib
import logging
from typing import Any, Optional, Sequence

from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("pipeline.import_utils")


def import_from_candidates(
    candidates: Sequence[str],
    *,
    package: Optional[str] = None,
    description: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> Any:
    """Importa un simbolo provando una serie di moduli candidati.

    Ogni elemento di ``candidates`` deve avere la forma ``"package.module:attr"``
    oppure ``"package.module"`` (in questo caso viene restituito il modulo stesso).
    I nomi relativi (``.`` o ``..``) sono supportati passando ``package``.

    Args:
        candidates: lista di moduli/attributi da tentare in ordine.
        package: package base per i nomi relativi (default: modulo chiamante).
        description: descrizione usata nel messaggio di errore finale.
        logger: logger opzionale per tracciare i tentativi di import.

    Returns:
        Il simbolo importato (modulo o attributo).

    Raises:
        ImportError: se nessuno dei candidati è stato importato con successo.
    """

    if not candidates:
        raise ImportError("Almeno un candidato è richiesto per l'import dinamico.")

    log = logger or LOGGER
    last_exc: Optional[Exception] = None

    for entry in candidates:
        module_name, sep, attr = entry.partition(":")
        try:
            module = importlib.import_module(module_name, package=package)
            return getattr(module, attr) if sep else module
        except Exception as exc:  # pragma: no cover - logging/fallback
            last_exc = exc
            log.debug(
                "import.candidate.failed",
                extra={
                    "candidate": entry,
                    "package": package or "",
                    "error": str(exc),
                },
            )

    desc = description or candidates[0]
    raise ImportError(f"Impossibile importare {desc}") from last_exc


__all__ = ["import_from_candidates"]
