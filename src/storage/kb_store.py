# SPDX-License-Identifier: GPL-3.0-only
# path: src/storage/kb_store.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kb_db import get_db_path


@dataclass(frozen=True)
class KbStore:
    """
    Owner esplicito del percorso del DB SQLite della KB.

    Design:
    - Oggi wrappa il default globale esistente (`kb_db.get_db_path()` sotto `data/`).
    - Domani potrà evolvere verso un DB per slug/workspace senza dover toccare di nuovo
      il retriever: la risoluzione del path resta centralizzata qui.
    """

    db_path: Optional[Path] = None
    slug: Optional[str] = None

    @classmethod
    def default(cls) -> "KbStore":
        """
        Store di default: replica il comportamento attuale, DB unico globale sotto `data/`.
        """
        return cls(db_path=None, slug=None)

    @classmethod
    def for_slug(cls, slug: str, *, base_dir: Optional[Path] = None) -> "KbStore":
        """
        Placeholder per strategie future "un DB per slug" o per workspace.

        Comportamento attuale (backward compat):
        - Se base_dir è None, usa comunque il DB globale (db_path=None).
        - Se base_dir è fornito, continua a restituire db_path=None per mantenere la
          compatibilità.

        Futuro:
        - Questo metodo diventerà l'unico punto in cui si mappa uno slug a un file DB
          dedicato (es. `base_dir / "data" / f"kb_{slug}.sqlite"` o varianti per workspace).
        """
        normalized_slug = slug.strip()
        if not normalized_slug:
            return cls.default()
        return cls(db_path=None, slug=normalized_slug)

    def effective_db_path(self) -> Path:
        """
        Restituisce il path effettivo da usare in kb_db/retriever.

        Regole:
        - Se `self.db_path` è valorizzato, usalo tal quale (test e call-site avanzati).
        - Altrimenti delega a `kb_db.get_db_path()` per preservare il default globale.
        """
        if self.db_path is not None:
            return self.db_path
        return get_db_path()
