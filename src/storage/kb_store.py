# SPDX-License-Identifier: GPL-3.0-or-later
# src/storage/kb_store.py
"""
Ownership esplicita del percorso DB della Knowledge Base.

Questo modulo incapsula la policy di mapping tra slug cliente e file SQLite nel modello
slug/workspace-based (nessuna risoluzione globale implicita).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pipeline.beta_flags import is_test_mode
from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within, ensure_within_and_resolve

__all__ = ["KbStore"]


@dataclass(frozen=True)
class KbStore:
    """
    Owner esplicito del percorso del DB SQLite della KB.

    Design:
    - Supporta solo i DB per workspace/slug.
    - La risoluzione del path è centralizzata qui: i call-site lavorano solo con slug/repo_root_dir
      o override espliciti.
    """

    slug: Optional[str] = None
    repo_root_dir: Optional[Path] = None
    db_path_override: Optional[Path] = None

    @classmethod
    def for_slug(cls, slug: str, *, repo_root_dir: Optional[Path] = None, db_path: Optional[Path] = None) -> "KbStore":
        """
        Costruisce uno store per uno slug/workspace specifico.

        Comportamento:
        - Se `db_path` è valorizzato: verrà usato come override esplicito (tipico dei test).
        - Se `db_path` è None ma `repo_root_dir` è valorizzato: verrà usato `repo_root_dir/semantic/kb.sqlite`
          (validato con path-safety).
        - Se `repo_root_dir` è None: viene sollevato un errore (nessuna risoluzione globale implicita).
        """
        normalized_slug = slug.strip()
        if not normalized_slug:
            raise ConfigError("KbStore.for_slug: lo slug non può essere vuoto nel flusso 1.0.")
        return cls(slug=normalized_slug, repo_root_dir=repo_root_dir, db_path_override=db_path)

    def effective_db_path(self) -> Path:
        """
        Restituisce il path effettivo da usare in kb_db/retriever.

        Regole:
        - Se `db_path_override` è valorizzato:
            - se è assoluto: usalo tal quale;
            - se è relativo e `repo_root_dir` è valorizzato: ancoralo sotto `repo_root_dir` con path-safety;
            - se è relativo e `repo_root_dir` è None: solleva un errore (nessuna risoluzione globale implicita).
        - Se non c'è override ma `repo_root_dir` è valorizzato: usa `repo_root_dir/semantic/kb.sqlite`
          validato con `ensure_within_and_resolve`.
        - Se non c'è né override né repo_root_dir: alleva un errore (risoluzione globale implicita rimossa).
        """
        test_mode = is_test_mode()
        if self.db_path_override is not None:
            override_path = Path(self.db_path_override)
            if not test_mode:
                payload_path = str(override_path.resolve()) if override_path.is_absolute() else str(override_path)
                raise ConfigError(
                    "KbStore: db_path_override consentito solo in TEST_MODE per il debugging.",
                    code="kb.db_path.override_forbidden",
                    slug=self.slug,
                    file_path=payload_path,
                )
            if override_path.is_absolute():
                resolved = override_path.resolve()
                if self.repo_root_dir is None:
                    raise ConfigError(
                        "KbStore: db_path assoluto richiede workspace root per validare il perimetro.",
                        code="kb.db_path.outside_workspace",
                        slug=self.slug,
                        file_path=resolved,
                    )
                repo_root_dir = Path(self.repo_root_dir).resolve()
                try:
                    ensure_within(repo_root_dir, resolved)
                except Exception as exc:
                    raise ConfigError(
                        "KbStore: db_path fuori dal workspace root.",
                        code="kb.db_path.outside_workspace",
                        slug=self.slug,
                        file_path=resolved,
                    ) from exc
                return resolved
            if self.repo_root_dir is not None:
                repo_root_dir = Path(self.repo_root_dir).resolve()
                perimeter_root = repo_root_dir
                candidate = repo_root_dir / override_path
                return ensure_within_and_resolve(perimeter_root, candidate)
            raise ConfigError("KbStore: db_path relativo senza repo_root_dir non è supportato.")

        if self.repo_root_dir is not None:
            repo_root_dir = Path(self.repo_root_dir).resolve()
            perimeter_root = repo_root_dir
            candidate = repo_root_dir / "semantic" / "kb.sqlite"
            resolved = ensure_within_and_resolve(perimeter_root, candidate)
            if not test_mode:
                self._assert_canonical_path(resolved, repo_root_dir)
            return resolved

        raise ConfigError("KbStore richiede slug/repo_root_dir espliciti; risoluzione globale implicita rimossa.")

    def _assert_canonical_path(self, resolved: Path, repo_root_dir: Path) -> None:
        canonical_semantic = (repo_root_dir / "semantic").resolve()
        if resolved.name != "kb.sqlite" or resolved.parent != canonical_semantic:
            raise ConfigError(
                "KbStore: runtime supporta solo <workspace>/semantic/kb.sqlite.",
                code="kb.db_path.non_canonical",
                slug=self.slug,
                file_path=str(resolved),
            )
