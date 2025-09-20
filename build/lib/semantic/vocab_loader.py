# src/semantic/vocab_loader.py
"""Loader del vocabolario canonico (SSoT) da SQLite.

Espone:
- load_reviewed_vocab(base_dir, logger) -> dict: {canonical: {"aliases": set[str]}}

Note sicurezza (lettura):
- Usare sempre `ensure_within_and_resolve(base, target)` per prevenire traversal (../, symlink).
- Il path YAML legacy viene solo usato per derivare il path del DB tramite storage.tags_store.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Set

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within, ensure_within_and_resolve
from storage.tags_store import derive_db_path_from_yaml_path
from storage.tags_store import load_tags_reviewed as load_tags_reviewed_db

__all__ = ["load_reviewed_vocab"]


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    """Carica il vocabolario consolidato da `semantic/tags.db` (YAML solo legacy).

    Sicurezza path: consente letture solo sotto `base_dir/semantic` e risolve il path YAML legacy.
    Ritorna un mapping con alias normalizzati per ogni canonical.
    """
    raw_yaml_path = base_dir / "semantic" / "tags_reviewed.yaml"
    try:
        # Resolve + guard in lettura: ritorna il path YAML già normalizzato
        safe_yaml_path = ensure_within_and_resolve(base_dir / "semantic", raw_yaml_path)
    except ConfigError:
        logger.warning(
            "tags_reviewed.yaml fuori da semantic/: skip lettura",
            extra={"file_path": str(raw_yaml_path)},
        )
        return {}

    try:
        # DB derivato dal percorso YAML legacy (compat con storage.tags_store)
        db_path = derive_db_path_from_yaml_path(safe_yaml_path)
        # Path-safety addizionale: assicurati che il DB ricada sotto semantic/
        ensure_within(base_dir / "semantic", db_path)
        if not Path(db_path).exists():
            logger.error(
                "tags.db non trovato: esegui il flusso di tagging per generarlo",
                extra={"file_path": str(db_path)},
            )
            raise ConfigError(
                "Vocabolario semantico mancante (tags.db). Esegui tag_onboarding per generarlo.",
                file_path=str(db_path),
            )

        data = load_tags_reviewed_db(db_path) or {}
        items = data.get("tags", []) or []

        vocab: Dict[str, Dict[str, Set[str]]] = {}

        # Azione: keep -> crea/aggiorna il canonical con i suoi sinonimi
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            action = str(it.get("action", "")).strip().lower()
            synonyms = [s for s in (it.get("synonyms") or []) if isinstance(s, str)]
            if not name:
                continue
            if action == "keep":
                entry = vocab.setdefault(name, {"aliases": set()})
                entry["aliases"].add(name)
                entry["aliases"].update({s for s in synonyms if s.strip()})

        # Azione: merge_into:<target> -> fonde alias dentro il target
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            action = str(it.get("action", "")).strip().lower()
            synonyms = [s for s in (it.get("synonyms") or []) if isinstance(s, str)]
            if not name or not action.startswith("merge_into:"):
                continue
            target = action.split(":", 1)[1].strip()
            if not target:
                continue
            entry = vocab.setdefault(target, {"aliases": set()})
            entry["aliases"].add(name)
            entry["aliases"].update({s for s in synonyms if s.strip()})

        if not vocab:
            logger.warning(
                "tags.db esistente ma senza canonici: completa la revisione/tagging",
                extra={"file_path": str(db_path)},
            )
            return {}

        logger.info("Vocabolario reviewed caricato", extra={"canonicals": len(vocab)})
        return vocab

    except (OSError, AttributeError) as e:
        logger.warning(
            "Impossibile leggere tags dal DB",
            extra={"file_path": str(raw_yaml_path), "error": str(e)},
        )
    except (ValueError, TypeError) as e:
        logger.warning(
            "Impossibile parsare dati tags dal DB",
            extra={"file_path": str(raw_yaml_path), "error": str(e)},
        )
    return {}
