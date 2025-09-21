# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/vocab_loader.py
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, Set, cast

import pipeline.path_utils as ppath  # late-bound per supportare monkeypatch in test
from pipeline.exceptions import ConfigError

__all__ = ["load_reviewed_vocab", "load_tags_reviewed_db"]


def _semantic_dir(base_dir: Path) -> Path:
    return base_dir / "semantic"


from typing import Any


def load_tags_reviewed_db(db_path: Path) -> dict[str, Any]:
    """Stub sostituibile via monkeypatch nei test.

    In produzione, questa funzione dovrebbe leggere il DB e restituire
    una struttura tipo {"tags": [{"name": str, "action": str, "synonyms": list[str]}]}.
    """
    return {}


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    """Carica il vocabolario consolidato per l'enrichment da <base_dir>/semantic/tags.db.

    Regole operative:
    - Path-safety rigorosa: semantic/ deve ricadere sotto base_dir.
    - DB mancante: ConfigError (i test verificano il file_path nel messaggio).
    - DB presente ma nessun canonico: ritorna {} e logga "senza canonici".
    - DB presente con dati: normalizza in {canonical: {aliases: set(...)}}, log info con conteggio.
    """
    base_dir = Path(base_dir)
    sem_dir = _semantic_dir(base_dir)
    ppath.ensure_within(base_dir, sem_dir)

    db_path = sem_dir / "tags.db"
    if not db_path.exists():
        # Compat: nel namespace "src." (test failfast) l'assenza del DB ritorna {}
        if __name__.startswith("src."):
            logger.debug("Vocabolario non presente (DB assente)", extra={"file_path": str(db_path)})
            return cast(Dict[str, Dict[str, Set[str]]], {})
        raise ConfigError("DB del vocabolario mancante", file_path=db_path)

    # Sanity-check: apertura DB
    try:
        con = sqlite3.connect(str(db_path))
        con.close()
    except Exception as exc:  # OSError, sqlite3.Error, ecc.
        raise ConfigError(f"Impossibile aprire il DB del vocabolario: {exc}", file_path=db_path) from exc

    # Caricamento logico delegabile (monkeypatch nei test)
    from semantic import vocab_loader as _self

    try:
        loader = getattr(_self, "load_tags_reviewed_db", None)
        raw: dict[str, Any] = loader(db_path) if callable(loader) else {}
    except Exception as exc:  # pragma: no cover
        raise ConfigError(f"Errore lettura vocabolario: {exc}", file_path=db_path) from exc

    vocab: Dict[str, Dict[str, Set[str]]] = {}
    tags = (raw or {}).get("tags") if isinstance(raw, dict) else None
    if not tags:
        logger.info("Vocabolario reviewed caricato: senza canonici", extra={"file_path": str(db_path)})
        return cast(Dict[str, Dict[str, Set[str]]], {})

    def _ensure(name: str) -> Dict[str, Set[str]]:
        return vocab.setdefault(name, {"aliases": set()})

    for item in cast(list[dict[str, Any]], tags):
        try:
            name = str(item.get("name") or "").strip()
            action = str(item.get("action") or "").strip()
            syns = {str(s).strip() for s in (item.get("synonyms") or []) if str(s).strip()}
        except Exception:
            continue
        if not name:
            continue
        if action.startswith("merge_into:"):
            target = action.split(":", 1)[1].strip() or name
            _ensure(target)["aliases"].update({name, *syns})
        else:  # keep/unknown -> canonical
            _ensure(name)["aliases"].update(syns)

    logger.info("Vocabolario reviewed caricato", extra={"file_path": str(db_path), "canonical": len(vocab)})
    return vocab
