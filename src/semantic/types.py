# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

__all__ = ["Vector", "EmbeddingsClient", "ClientContextProtocol", "SemanticContextProtocol"]


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
      - repo_root_dir: unico punto di verità per risolvere WorkspaceLayout
      - slug: identificatore logico del cliente
    """

    # SSoT per risolvere WorkspaceLayout
    repo_root_dir: Path

    # Metadato logico
    slug: str


@runtime_checkable
class SemanticContextProtocol(ClientContextProtocol, Protocol):
    """Contratto esplicito per i workflow semantici.

    Estende il contesto minimo con i flag UX usati dalla CLI/UI (es. preview, interattività).
    """

    skip_preview: bool
    no_interactive: bool
