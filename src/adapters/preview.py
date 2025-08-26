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

import re
from typing import Optional, Any

from pipeline.exceptions import ConfigError
from pipeline.gitbook_preview import run_gitbook_docker_preview, stop_container_safely

__all__ = ["start_preview", "stop_preview"]

# Regola conservativa per nomi container Docker
_CONTAINER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def _default_container_name(context: Any) -> str:
    slug = getattr(context, "slug", "kb")
    # hardening: slug “docker-friendly”
    safe_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(slug)).strip("-") or "kb"
    return f"gitbook-{safe_slug}"


def _validate_port(port: int) -> None:
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ConfigError(f"Porta non valida per preview: {port}")


def _validate_container_name(name: str) -> None:
    if not name or not _CONTAINER_RE.match(name):
        raise ConfigError(f"Nome container non valido: '{name}'")


def start_preview(
    context: Any,
    logger,
    *,
    port: int = 4000,
    container_name: Optional[str] = None,
) -> str:
    """
    Avvia la preview HonKit in modalità detached e ritorna il nome del container.

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
            wait_on_exit=False,  # sempre detached per semplicità dell’orchestratore
            redact_logs=redact,
        )
        logger.info("Preview avviata", extra={"container": cname, "port": port, "redact_logs": redact})
        return cname
    except Exception as e:
        logger.error("Avvio preview fallito", extra={"container": cname, "port": port, "error": str(e)})
        raise ConfigError(f"Avvio preview fallito: {e}")


def stop_preview(logger, *, container_name: Optional[str]) -> None:
    """
    Ferma la preview in modo sicuro (best-effort). Non solleva se il container non esiste.

    Args:
        logger: logger strutturato.
        container_name: nome del container da fermare; se falsy non fa nulla.
    """
    if not container_name:
        logger.debug("Nessun container_name fornito: skip stop_preview.")
        return

    # Validazione “soft”: se non valido, log avviso e interrompiamo (best-effort)
    if not _CONTAINER_RE.match(container_name):
        logger.warning("Nome container non valido: skip stop_preview.", extra={"container": container_name})
        return

    try:
        stop_container_safely(container_name)
        logger.info("Preview Docker fermata", extra={"container": container_name})
    except Exception as e:  # best-effort
        logger.warning("Stop preview fallito (best-effort)", extra={"container": container_name, "error": str(e)})
