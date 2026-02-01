# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, cast

from pipeline.exceptions import ConfigError
from pipeline.workspace_layout import WorkspaceLayout
from ui.clients_store import get_all as get_clients
from ui.utils.workspace import resolve_raw_dir

T = TypeVar("T")


def repo_root(manage_file: Path) -> Path:
    """Restituisce la root del repository partendo dal file della pagina manage."""
    candidate = manage_file.resolve()
    for _ in range(3):
        candidate = candidate.parent
    return candidate


def clients_db_path(manage_file: Path) -> Path:
    """Percorso al file clients_db/clients.yaml partendo da manage.py."""
    return repo_root(manage_file) / "clients_db" / "clients.yaml"


def workspace_root(slug: str, *, layout: WorkspaceLayout | None = None) -> Path:
    """
    Helper storico: restituisce la root workspace.

    In contesti moderni dove il layout è disponibile, preferire `layout.repo_root_dir` direttamente.
    Questo wrapper rimane per non modificare le chiamate esistenti dalla pagina `manage`.
    """
    if layout is not None:
        return cast(Path, layout.repo_root_dir)
    raw_dir = Path(resolve_raw_dir(slug))
    return raw_dir.parent


def load_clients(logger: Any, manage_file: Path) -> list[dict[str, Any]]:
    """Carica l'elenco clienti delegando allo store centrale."""
    try:
        return [entry.to_dict() for entry in get_clients()]
    except ConfigError as exc:
        logger.info(
            "ui.manage.clients.unavailable",
            extra={"code": getattr(exc, "code", None), "path": str(clients_db_path(manage_file))},
        )
        return []
    except Exception as exc:  # pragma: no cover - logging degradato
        logger.warning(
            "ui.manage.clients.load_error",
            extra={"error": str(exc), "path": str(clients_db_path(manage_file))},
        )
        return []


def safe_get(fn_path: str) -> Optional[Callable[..., Any]]:
    """Importa una funzione (modulo:callable) se disponibile, altrimenti None."""
    try:
        pkg, func = fn_path.split(":")
        module = __import__(pkg, fromlist=[func])
        candidate = getattr(module, func, None)
        return candidate if callable(candidate) else None
    except Exception:  # pragma: no cover - risoluzioni opzionali
        return None


def call_strict(fn: Callable[..., T], *, logger: Any, **kwargs: Any) -> T:
    """Chiama fn dopo aver validato gli kwargs contro la firma dichiarata."""
    sig = inspect.signature(fn)
    allowed = list(sig.parameters.keys())
    accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values())

    if not accepts_kwargs:
        unknown = sorted(set(kwargs) - set(sig.parameters))
        if unknown:
            raise TypeError(f"Unknown kwargs for {getattr(fn, '__name__', repr(fn))}: {unknown}. Allowed: {allowed}")

    try:
        sig.bind(**kwargs)
    except TypeError as exc:
        raise TypeError(f"Signature mismatch for {getattr(fn, '__name__', repr(fn))}: {exc}") from exc

    return fn(**kwargs)
