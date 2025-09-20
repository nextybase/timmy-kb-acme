from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

__all__ = ["Vector", "EmbeddingsClient", "ClientContextProtocol"]


# Vettore numerico generico per embeddings o simili
Vector = Sequence[float]


@runtime_checkable
class EmbeddingsClient(Protocol):
    """Contratto minimale per un client di embeddings.

    Implementazioni tipiche potrebbero wrappare servizi locali o remoti. L'interfaccia resta
    volutamente essenziale per ridurre il coupling.
    """

    def embed_texts(
        self: "EmbeddingsClient",
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> Sequence[Vector]: ...


@runtime_checkable
class ClientContextProtocol(Protocol):
    """Contratto strutturale **minimale** per il contesto cliente.

    Mantieni qui solo ciò che è realmente consumato dai servizi/orchestratori,
    così eviti dipendenze dure e cicliche:
      - base_dir: radice sicura per path-safety
      - raw_dir / md_dir: cartelle operative usate dai servizi di contenuto
      - slug: identificatore logico del cliente
    """

    # Radice percorso
    base_dir: Path

    # Cartelle operative
    raw_dir: Path
    md_dir: Path

    # Metadato logico
    slug: str
