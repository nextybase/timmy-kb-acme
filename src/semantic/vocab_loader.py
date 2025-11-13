# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/vocab_loader.py
from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Set, cast

import pipeline.path_utils as ppath  # late-bound per testability
from pipeline.constants import REPO_NAME_PREFIX
from pipeline.exceptions import ConfigError

__all__ = ["load_reviewed_vocab", "load_tags_reviewed_db"]

# Import lazy del loader reale; se assente, enrichment resta opzionale.
try:  # pragma: no cover - dipende dall'ambiente
    from storage.tags_store import load_tags_reviewed as _load_tags_reviewed
except Exception:  # pragma: no cover
    _load_tags_reviewed = None


def _to_vocab(data: Any) -> Dict[str, Dict[str, list[str]]]:
    """
    Normalizza data in: { canonical: { "aliases": [str,...] } } mantenendo l'ordine di inserimento.

    Formati accettati:
    - già normalizzato: Dict[str, Dict[str, Iterable[str]]]
    - mapping semplice: Dict[str, Iterable[str]]  (canonical -> aliases)
    - formato storage: {"tags": [{"name": str, "action": str, "synonyms": [str,...]}, ...]}
    - lista di dict:   [{"canonical": str, "alias": str}, ...]
    - lista di tuple:  [(canonical:str, alias:str), ...]
    - lista di liste:  [[canonical, alias], ...]
    - altro/non riconosciuto -> {}
    """
    out: Dict[str, list[str]] = defaultdict(list)
    seen_aliases: Dict[str, Set[str]] = defaultdict(set)

    def _append_alias(canon_value: Any, alias_value: Any) -> None:
        canon = str(canon_value)
        alias = str(alias_value)
        if not canon or not alias:
            return
        if alias in seen_aliases[canon]:
            return
        seen_aliases[canon].add(alias)
        out[canon].append(alias)

    # 1) già normalizzato o dizionario con chiave speciale 'tags'
    if isinstance(data, Mapping):
        sample_val = next(iter(data.values()), None)
        # già normalizzato
        if isinstance(sample_val, Mapping) and "aliases" in sample_val:
            result: Dict[str, Dict[str, list[str]]] = {}
            for canon, payload in cast(Mapping[str, Mapping[str, Iterable[str]]], data).items():
                aliases = payload.get("aliases", [])
                ordered: list[str] = []
                seen: set[str] = set()
                for alias in aliases or []:
                    alias_str = str(alias)
                    if not alias_str or alias_str in seen:
                        continue
                    seen.add(alias_str)
                    ordered.append(alias_str)
                result[str(canon)] = {"aliases": ordered}
            return result
        # formato storage: {"tags": [ {name, action, synonyms?}, ... ]}
        items = cast(Any, data).get("tags") if hasattr(data, "get") else None
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
            for row in items:
                if not isinstance(row, Mapping):
                    continue
                name = row.get("name")
                action = str(row.get("action", "")).strip().lower()
                syns = row.get("synonyms") or []

                target = None
                if action.startswith("merge_into:"):
                    target = action.split(":", 1)[1].strip()

                if action == "keep":
                    canon = str(name)
                    if canon:
                        if isinstance(syns, (list, tuple, set)):
                            for s in syns:
                                _append_alias(canon, s)
                        elif isinstance(syns, (str, bytes)) and str(syns).strip():
                            _append_alias(canon, syns)
                        out.setdefault(canon, out.get(canon, []))
                elif target:
                    canon = str(target)
                    alias = str(name)
                    if canon and alias:
                        _append_alias(canon, alias)
                        if isinstance(syns, (list, tuple, set)):
                            for s in syns:
                                _append_alias(canon, s)
                        elif isinstance(syns, (str, bytes)) and str(syns).strip():
                            _append_alias(canon, syns)
                        out.setdefault(canon, out.get(canon, []))
            if out:
                return {k: {"aliases": v} for k, v in out.items()}

        # mapping semplice: canon -> Iterable[alias]
        try:
            for canon, aliases in cast(Mapping[str, Iterable[Any]], data).items():
                if isinstance(aliases, (str, bytes)):
                    _append_alias(canon, aliases)
                else:
                    for a in aliases:
                        _append_alias(canon, a)
            return {k: {"aliases": v} for k, v in out.items()}
        except Exception:
            pass  # tenteremo i casi successivi

    # 2) lista di dict/tuple/list
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        for row in data:
            if isinstance(row, Mapping):
                canon = str(row.get("canonical") or row.get("canon") or row.get("c") or "")
                alias = str(row.get("alias") or row.get("a") or "")
                if isinstance(canon, (str, bytes)) and isinstance(alias, (str, bytes)):
                    _append_alias(canon, alias)
            elif isinstance(row, (tuple, list)) and len(row) >= 2:
                canon, alias = row[0], row[1]
                if isinstance(canon, (str, bytes)) and isinstance(alias, (str, bytes)):
                    _append_alias(canon, alias)
        if out:
            return {k: {"aliases": v} for k, v in out.items()}

    # 3) fallback: shape non riconosciuta
    return {}


def load_tags_reviewed_db(db_path: Path) -> Dict[str, Dict[str, list[str]]]:
    """
    Wrapper patchabile che carica i 'canonici' da tags.db e li adatta alla shape attesa.

    Se il modulo reale non è disponibile → {} (enrichment opzionale).
    """
    if _load_tags_reviewed is None:
        return {}
    try:
        raw = _load_tags_reviewed(str(db_path))  # accetta str/Path
    except sqlite3.Error as exc:  # errori SQLite (query/cursor)
        raise ConfigError(
            f"Errore lettura DB del vocabolario: {exc}",
            file_path=db_path,
        ) from exc
    return _to_vocab(raw)


def _semantic_dir(base_dir: Path) -> Path:
    return base_dir / "semantic"


def _derive_slug(base_dir: Path) -> str | None:
    name = Path(base_dir).name
    if not name:
        return None
    prefix = REPO_NAME_PREFIX
    if prefix and name.startswith(prefix):
        stripped = name[len(prefix) :]
        if stripped:
            return stripped
    return name


def _log_vocab_event(
    logger: logging.Logger,
    event: str,
    *,
    slug: str | None,
    file_path: Path,
    canon_count: int,
) -> None:
    try:
        logger.info(
            event,
            extra={
                "event": event,
                "slug": slug,
                "file_path": str(file_path),
                "canon_count": int(canon_count),
            },
        )
    except Exception:
        pass


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, list[str]]]:
    """
    Carica (se presente) il vocabolario consolidato per l'enrichment da semantic/tags.db.

    Regole:
    - Se `tags.db` non esiste: restituisce `{}` e registra un log informativo (enrichment disabilitato).
    - Errori di path (traversal/symlink) o apertura DB: `ConfigError` con metadati utili.
    - Dati letti adattati a: {canonical: {"aliases": [str,...]}}.
    """
    base_dir = Path(base_dir)
    # Path-safety forte con risoluzione reale
    sem_dir = ppath.ensure_within_and_resolve(base_dir, _semantic_dir(base_dir))
    db_path = ppath.ensure_within_and_resolve(sem_dir, sem_dir / "tags.db")
    slug = _derive_slug(base_dir)

    # DB assente: enrichment disabilitato (nessuna eccezione)
    if not db_path.exists():
        _log_vocab_event(
            logger,
            "semantic.vocab.db_missing",
            slug=slug,
            file_path=db_path,
            canon_count=0,
        )
        return {}

    try:
        con = sqlite3.connect(str(db_path))
        con.close()
    except Exception as exc:
        raise ConfigError(
            f"Impossibile aprire il DB del vocabolario: {exc}",
            file_path=db_path,
        ) from exc

    raw = load_tags_reviewed_db(db_path)
    vocab = _to_vocab(raw)
    if not vocab:
        _log_vocab_event(
            logger,
            "semantic.vocab.db_empty",
            slug=slug,
            file_path=db_path,
            canon_count=0,
        )
        return {}

    _log_vocab_event(
        logger,
        "semantic.vocab.loaded",
        slug=slug,
        file_path=db_path,
        canon_count=len(vocab),
    )
    return vocab
