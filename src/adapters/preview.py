# src/adapters/preview.py
"""
Adapter: gestione preview GitBook/HonKit.

Obiettivo (PR-2/PR-4):
- API semplice e uniforme per avviare/fermare la preview,
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

from typing import Optional
from pipeline.gitbook_preview import run_gitbook_docker_preview, stop_container_safely

__all__ = ["start_preview", "stop_preview"]


def _default_container_name(context) -> str:
    slug = getattr(context, "slug", "kb")
    return f"gitbook-{slug}"


def start_preview(
    context,
    logger,
    *,
    port: int = 4000,
    container_name: Optional[str] = None,
) -> str:
    """
    Avvia la preview HonKit in modalità detached e ritorna il nome del container.

    Args:
        context: ClientContext o oggetto compatibile (richiesto: .slug, .redact_logs opzionale).
        logger: logger strutturato.
        port: porta esposta in locale (default: 4000).
        container_name: nome esplicito del container; se None → "gitbook-<slug>".

    Returns:
        Il nome del container docker creato/riutilizzato.
    """
    cname = container_name or _default_container_name(context)
    redact = bool(getattr(context, "redact_logs", False))

    run_gitbook_docker_preview(
        context,
        port=port,
        container_name=cname,
        wait_on_exit=False,         # sempre detached per semplicità dell’orchestratore
        redact_logs=redact,
    )
    logger.info(
        "Preview avviata",
        extra={"container": cname, "port": port, "redact_logs": redact},
    )
    return cname


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
    try:
        stop_container_safely(container_name)
        logger.info("Preview Docker fermata", extra={"container": container_name})
    except Exception as e:  # best-effort
        logger.warning(
            "Stop preview fallito (best-effort)",
            extra={"container": container_name, "error": str(e)},
        )
