# SPDX-License-Identifier: GPL-3.0-only
# src/storage/kb_store.py
"""
Ownership esplicita del percorso DB della Knowledge Base.

Questo modulo incapsula la policy di mapping tra slug cliente e file SQLite:
- supporta override esplicito (test/advanced),
- supporta DB per workspace/slug (semantic/kb.sqlite sotto il workspace),
- mantiene fallback legacy sul DB globale sotto `data/` gestito da kb_db.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kb_db import get_db_path
from pipeline.path_utils import ensure_within_and_resolve

__all__ = ["KbStore"]


@dataclass(frozen=True)
class KbStore:
    """
    Owner esplicito del percorso del DB SQLite della KB.

    Design:
    - Supporta sia il DB globale legacy (data/kb.sqlite) sia i DB per workspace/slug.
    - La risoluzione del path è centralizzata qui: i call-site lavorano solo con slug/base_dir.
    """

    slug: Optional[str] = None
    base_dir: Optional[Path] = None
    db_path_override: Optional[Path] = None

    @classmethod
    def default(cls) -> "KbStore":
        """
        Store di default: replica il comportamento attuale, DB unico globale sotto `data/`.
        """
        return cls(slug=None, base_dir=None, db_path_override=None)

    @classmethod
    def for_slug(cls, slug: str, *, base_dir: Optional[Path] = None, db_path: Optional[Path] = None) -> "KbStore":
        """
        Costruisce uno store per uno slug/workspace specifico.

        Comportamento:
        - Se `db_path` è valorizzato: verrà usato come override esplicito (tipico dei test).
        - Se `db_path` è None ma `base_dir` è valorizzato: verrà usato `base_dir/semantic/kb.sqlite`
          (validato con path-safety).
        - Se sia `db_path` che `base_dir` sono None: fallback al DB globale.
        """
        normalized_slug = slug.strip()
        if not normalized_slug:
            return cls.default()
        return cls(slug=normalized_slug, base_dir=base_dir, db_path_override=db_path)

    def effective_db_path(self) -> Path:
        """
        Restituisce il path effettivo da usare in kb_db/retriever.

        Regole:
        - Se `db_path_override` è valorizzato:
            - se è assoluto: usalo tal quale;
            - se è relativo e `base_dir` è valorizzato: ancoralo sotto `base_dir` con path-safety;
            - se è relativo e `base_dir` è None: delega a kb_db (sarà ancorato a `data/`).
        - Se non c'è override ma `base_dir` è valorizzato: usa `base_dir/semantic/kb.sqlite`
          validato con `ensure_within_and_resolve`.
        - Se non c'è né override né base_dir: fallback a `get_db_path()` (DB globale sotto `data/`).
        """
        if self.db_path_override is not None:
            p = Path(self.db_path_override)
            if p.is_absolute():
                return p.resolve()
            if self.base_dir is not None:
                base = Path(self.base_dir).resolve()
                candidate = base / p
                return ensure_within_and_resolve(base, candidate)
            return self.db_path_override

        if self.base_dir is not None:
            base = Path(self.base_dir).resolve()
            candidate = base / "semantic" / "kb.sqlite"
            return ensure_within_and_resolve(base, candidate)

        return get_db_path()
