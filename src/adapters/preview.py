# SPDX-License-Identifier: GPL-3.0-only
# src/adapters/preview.py
"""
Adapter: gestione preview GitBook/HonKit.

Obiettivo:
- API semplice ed uniforme per avviare/fermare la preview,
  incapsulando le call di basso livello al modulo pipeline.
- Firma coerente: (context, logger, *, port=4000, container_name=None).

API:
- start_preview(context, logger, *, port=4000, container_name=None) -> str
- stop_preview(logger, *, container_name: str) -> None

Note:
- Propaga automaticamente `context.redact_logs` a run_gitbook_docker_preview.
- Se `container_name` non è fornito, usa `gitbook-<slug>` come default.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Protocol, runtime_checkable

from pipeline.exceptions import ConfigError
from pipeline.honkit_preview import run_gitbook_docker_preview, stop_container_safely

__all__ = ["start_preview", "stop_preview"]

# Regola conservativa per nomi container Docker
_CONTAINER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


@runtime_checkable
class _PreviewContext(Protocol):
    @property
    def slug(self) -> str: ...

    @property
    def redact_logs(self) -> bool: ...


def _default_container_name(context: _PreviewContext | object) -> str:
    slug = getattr(context, "slug", "kb")
    # hardening: slug "docker-friendly"
    safe_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(slug)).strip("-") or "kb"
    return f"gitbook-{safe_slug}"


def _validate_port(port: int) -> None:
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ConfigError(f"Porta non valida per preview: {port}")


def _validate_container_name(name: str) -> None:
    if not name or not _CONTAINER_RE.match(name):
        raise ConfigError(f"Nome container non valido: '{name}'")


def _docker_unavailable_hint(msg: str) -> str | None:
    """Ritorna un messaggio standard se sembra che Docker non sia attivo."""
    m = (msg or "").lower()
    patterns = (
        "docker",
        "daemon",
        "dockerd",
        "cannot connect",
        "connection refused",
        "is the docker daemon running",
        "error while fetching server api version",
    )
    if any(p in m for p in patterns):
        return "Docker non attivo: avvia Docker Desktop e riprova."
    return None


def start_preview(
    context: _PreviewContext | object,
    logger: logging.Logger,
    *,
    port: int = 4000,
    container_name: str | None = None,
) -> str:
    """Avvia la preview HonKit in modalità detached e ritorna il nome del container.

    Args:
        context: ClientContext o compatibile (richiesti: .slug; opzionale: .redact_logs).
        logger: logger strutturato.
        port: porta esposta in locale (default: 4000).
        container_name: nome esplicito del container; se None → "gitbook-<slug>".

    Returns:
        Il nome del container docker creato/riutilizzato.

    Raises:
        ConfigError: se parametri non validi o avvio fallito.
    """
    _validate_port(port)
    cname = container_name or _default_container_name(context)
    _validate_container_name(cname)

    redact = bool(getattr(context, "redact_logs", False))
    try:
        run_gitbook_docker_preview(
            context,
            port=port,
            container_name=cname,
            wait_on_exit=False,  # sempre detached per semplicità dell'orchestratore
            redact_logs=redact,
        )
        logger.info(
            "adapter.preview.started",
            extra={"container": cname, "port": port, "redact_logs": redact, "slug": getattr(context, "slug", None)},
        )
        return cname
    except Exception as e:
        hint = _docker_unavailable_hint(str(e))
        if hint:
            logger.warning(
                "adapter.preview.docker_unavailable",
                extra={"container": cname, "port": port, "error": str(e), "slug": getattr(context, "slug", None)},
            )
            raise ConfigError(hint)
        logger.error(
            "adapter.preview.start_failed",
            extra={"container": cname, "port": port, "error": str(e), "slug": getattr(context, "slug", None)},
        )
        raise ConfigError("Avvio preview fallito.")


def stop_preview(logger: logging.Logger, *, container_name: Optional[str]) -> None:
    """Ferma la preview in modo sicuro (best-effort, non influenza artefatti/gate/ledger/exit code).
    Non solleva se il container non esiste.

    Args:
        logger: logger strutturato.
        container_name: nome del container da fermare; se falsy non fa nulla.
    """
    if not container_name:
        logger.debug("adapter.preview.stop.skip_no_name", extra={"container": None})
        return

    # Validazione "soft": se non valido, log avviso e interrompiamo (best-effort, no effetti su gate/ledger).
    if not _CONTAINER_RE.match(container_name):
        logger.warning(
            "adapter.preview.stop.invalid_name",
            extra={"container": container_name},
        )
        return

    try:
        stop_container_safely(container_name)
        logger.info("adapter.preview.stopped", extra={"container": container_name})
    except Exception as e:  # best-effort (non influenza artefatti/gate/ledger/exit code)
        hint = _docker_unavailable_hint(str(e))
        if hint:
            logger.warning(
                "adapter.preview.stop.docker_unavailable",
                extra={"container": container_name, "error": str(e)},
            )
            return
        logger.warning(
            "adapter.preview.stop_failed",
            extra={"container": container_name, "error": str(e)},
        )
