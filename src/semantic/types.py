from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


__all__ = ["Vector", "EmbeddingsClient", "ClientContextProtocol"]


# Vettore numerico generico per embeddings o simili
Vector = Sequence[float]


@runtime_checkable
class EmbeddingsClient(Protocol):
    """Contratto minimale per un client di embeddings.

    Implementazioni tipiche potrebbero wrappare servizi locali o remoti.
    L'interfaccia resta volutamente essenziale per ridurre il coupling.
    """

    def embed_texts(
        self: "EmbeddingsClient",
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> Sequence[Vector]: ...


@runtime_checkable
class ClientContextProtocol(Protocol):
    """Contratto strutturale minimale per il contesto cliente usato dalla façade.

    Mantieni qui solo ciò che è realmente consumato dai servizi/orchestratori,
    così eviti dipendenze dure e cicliche:
      - base_dir / repo_root: radice sicura per path-safety
      - slug: identificatore logico del cliente
      - logger: logging già configurato
      - config: mappa di configurazione (opzionale, dipende dai moduli)
      - raw_dir / md_dir: cartelle usate più spesso nei servizi di contenuto
    """

    # Radici percorso (almeno una delle due è comunemente presente)
    base_dir: Path
    repo_root: Path  # se non esiste nel contesto reale, può essere alias di base_dir

    # Cartelle operative più comuni
    raw_dir: Path
    md_dir: Path

    # Metadati/servizi
    slug: str
    logger: logging.Logger
    config: Mapping[str, Any]
