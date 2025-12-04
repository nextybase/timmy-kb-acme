# SPDX-License-Identifier: GPL-3.0-only
# src/storage/kb_store.py
"""
Ownership esplicita del percorso DB della Knowledge Base.

Questo modulo incapsula la policy di mapping tra slug cliente e file SQLite:
- oggi consente override esplicito e, in mancanza, deriva un path per slug sotto data/ (risolto da kb_db).
- evita che i call-site decidano il path in modo sparso; kb_db resta l'autorità per path-safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = ["KbStore"]


@dataclass(frozen=True)
class KbStore:
    """Piccolo oggetto che incapsula la policy di path per il DB KB.

    - `slug`: identifica il tenant (cliente/progetto), può anche essere stringa vuota.
    - `db_path_override`: path esplicito per test o override.
    """

    slug: str
    db_path_override: Optional[Path] = None

    @classmethod
    def for_slug(cls, slug: str, db_path: Optional[Path] = None) -> "KbStore":
        """Factory per costruire uno store legato a uno slug, con eventuale override esplicito."""
        return cls(slug=str(slug), db_path_override=db_path)

    def effective_db_path(self) -> Optional[Path]:
        """Restituisce il path da passare a kb_db.

        Regole:
        - Se c'è un override esplicito -> restituiscilo (assoluto o relativo).
        - Se `slug` non è vuoto -> ritorna un path RELATIVO basato sullo slug
          (kb_db._resolve_db_path lo ancora sotto `data/`): Path(f"kb-{slug}.sqlite")
        - Se slug è vuoto e non c'è override -> restituisci None (kb_db userà `data/kb.sqlite`).

        Nota: path-safety/ancoraggio a `data/` resta responsabilità di kb_db._resolve_db_path.
        """
        if self.db_path_override is not None:
            return self.db_path_override
        if self.slug:
            return Path(f"kb-{self.slug}.sqlite")
        return None
