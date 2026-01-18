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
from pipeline.logging_utils import get_structured_logger

__all__ = ["load_reviewed_vocab", "load_tags_reviewed_db"]

# Import lazy del loader reale; se assente, enrichment resta opzionale.
LOGGER = get_structured_logger("semantic.vocab_loader")

try:  # pragma: no cover - dipende dall'ambiente
    from storage.tags_store import load_tags_reviewed as _load_tags_reviewed
except Exception as exc:  # pragma: no cover
    _load_tags_reviewed = None
    LOGGER.warning(
        "semantic.vocab_loader.stubbed",
        extra={"error": str(exc)},
    )


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
        canon = str(canon_value).strip().casefold()
        alias = str(alias_value).strip()
        if not canon or not alias:
            return
        if alias in seen_aliases[canon]:
            return
        seen_aliases[canon].add(alias)
        out[canon].append(alias)

    def _build_from_tag_rows(rows: Sequence[Any]) -> Dict[str, Dict[str, list[str]]]:
        synonym_map: dict[str, list[str]] = defaultdict(list)
        synonym_seen: dict[str, set[str]] = defaultdict(set)
        merge_map: dict[str, str] = {}
        display_names: dict[str, str] = {}
        case_conflicts: set[str] = set()

        def _normalize_synonyms(raw: Any) -> list[str]:
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                return [str(item).strip() for item in raw if str(item).strip()]
            if isinstance(raw, (str, bytes)):
                value = str(raw).strip()
                return [value] if value else []
            return []

        def _record_synonym(target: str, alias_value: str) -> None:
            alias_str = alias_value.strip()
            if not alias_str:
                return
            key = alias_str.casefold()
            if key in synonym_seen[target]:
                return
            synonym_seen[target].add(key)
            synonym_map[target].append(alias_str)

        def _resolve_target(name: str) -> str:
            visited: set[str] = set()
            current = name
            while True:
                next_target = merge_map.get(current)
                if not next_target or next_target in visited:
                    break
                visited.add(current)
                current = next_target
            return current

        final_aliases: dict[str, list[str]] = defaultdict(list)
        final_seen: dict[str, set[str]] = defaultdict(set)

        def _ensure_target(target: str) -> None:
            final_aliases.setdefault(target, [])
            final_seen.setdefault(target, set())

        def _add_final_alias(target: str, alias_value: str) -> None:
            alias_str = alias_value.strip()
            if not alias_str:
                return
            lower = alias_str.casefold()
            if lower in final_seen[target]:
                return
            final_seen[target].add(lower)
            final_aliases[target].append(alias_str)

        for row in rows:
            if not isinstance(row, Mapping):
                continue
            raw_name = str(row.get("name") or row.get("canonical") or "").strip()
            if not raw_name:
                continue
            name = raw_name.casefold()
            existing_display = display_names.get(name)
            if existing_display and existing_display != raw_name and name not in case_conflicts:
                case_conflicts.add(name)
                try:
                    LOGGER.warning(
                        "semantic.vocab.canonical_case_conflict",
                        extra={
                            "canonical_norm": name,
                            "canonical": existing_display,
                            "canonical_new": raw_name,
                        },
                    )
                except Exception:
                    pass
            display_names.setdefault(name, raw_name)
            raw_action = str(row.get("action", "")).strip()
            action = raw_action.lower()
            synonym_map.setdefault(name, [])
            synonym_seen.setdefault(name, set())
            raw_syns = row.get("synonyms") or row.get("aliases") or []
            for alias in _normalize_synonyms(raw_syns):
                _record_synonym(name, alias)
            if action.startswith("merge_into:"):
                parts = raw_action.split(":", 1)
                target_raw = parts[1].strip() if len(parts) > 1 else ""
                if target_raw:
                    target_norm = target_raw.casefold()
                    merge_map[name] = target_norm
                    existing_target = display_names.get(target_norm)
                    if existing_target and existing_target != target_raw and target_norm not in case_conflicts:
                        case_conflicts.add(target_norm)
                        try:
                            LOGGER.warning(
                                "semantic.vocab.canonical_case_conflict",
                                extra={
                                    "canonical_norm": target_norm,
                                    "canonical": existing_target,
                                    "canonical_new": target_raw,
                                },
                            )
                        except Exception:
                            pass
                    display_names.setdefault(target_norm, target_raw)

        # Deduce merge relationships for canonical entries that appear as aliases elsewhere.
        for canon, aliases in list(synonym_map.items()):
            for alias in aliases:
                alias_norm = alias.casefold()
                if alias_norm in synonym_map and alias_norm != canon and alias_norm not in merge_map:
                    merge_map[alias_norm] = canon

        all_names = set(synonym_map.keys()) | set(merge_map.keys()) | set(merge_map.values())
        for name in all_names:
            target = _resolve_target(name)
            if not target:
                continue
            _ensure_target(target)
            if name != target:
                _add_final_alias(target, display_names.get(name, name))
            for alias in synonym_map.get(name, []):
                _add_final_alias(target, alias)

        return {display_names.get(canon, canon): {"aliases": aliases} for canon, aliases in final_aliases.items()}

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
            processed = _build_from_tag_rows(items)
            if processed:
                return processed

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
        LOGGER.warning(
            "semantic.vocab.loader_missing",
            extra={"event": "semantic.vocab.loader_missing", "file_path": str(db_path)},
        )
        raise ConfigError("Loader tags_store mancante per tags.db.", file_path=db_path)
    try:
        raw = _load_tags_reviewed(str(db_path))  # accetta str/Path
    except sqlite3.Error as exc:  # errori SQLite (query/cursor)
        err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
        err_type = type(exc).__name__
        raise ConfigError(
            f"Errore lettura DB del vocabolario: {err_type}: {err_line}",
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
    except Exception as exc:
        logger.warning(
            "semantic.vocab.log_failed",
            extra={"event": event, "error": str(exc), "slug": slug},
        )


def load_reviewed_vocab(
    base_dir: Path,
    logger: logging.Logger,
    *,
    strict: bool = False,
) -> Dict[str, Dict[str, list[str]]]:
    """
    Carica (se presente) il vocabolario consolidato per l'enrichment da semantic/tags.db.

    Regole:
    - Se `tags.db` non esiste: solleva `ConfigError` dopo log informativo.
    - Errori di path (traversal/symlink) o apertura DB: `ConfigError` con metadati utili.
    - Dati letti adattati a: {canonical: {"aliases": [str,...]}}.
    """
    base_dir = Path(base_dir)
    # Path-safety forte con risoluzione reale
    sem_dir = ppath.ensure_within_and_resolve(base_dir, _semantic_dir(base_dir))
    db_path = ppath.ensure_within_and_resolve(sem_dir, sem_dir / "tags.db")
    slug = _derive_slug(base_dir)

    # DB assente: stop hard
    if not db_path.exists():
        _log_vocab_event(
            logger,
            "semantic.vocab.db_missing",
            slug=slug,
            file_path=db_path,
            canon_count=0,
        )
        raise ConfigError("Vocabolario canonico assente (tags.db).", file_path=db_path)

    if _load_tags_reviewed is None:
        if strict:
            raise ConfigError("Loader tags_store mancante in modalità strict.", file_path=db_path)
        logger.warning(
            "semantic.vocab.tags_store_missing",
            extra={"slug": slug, "file_path": str(db_path)},
        )
        raise ConfigError("Loader tags_store mancante per tags.db.", file_path=db_path)

    try:
        con = sqlite3.connect(str(db_path))
        con.close()
    except Exception as exc:
        err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
        err_type = type(exc).__name__
        raise ConfigError(
            f"Impossibile aprire il DB del vocabolario: {err_type}: {err_line}",
            file_path=db_path,
        ) from exc

    vocab_raw = load_tags_reviewed_db(db_path)
    vocab = _to_vocab(vocab_raw)
    if not vocab:
        _log_vocab_event(
            logger,
            "semantic.vocab.db_empty",
            slug=slug,
            file_path=db_path,
            canon_count=0,
        )
        raise ConfigError("Vocabolario canonico vuoto (tags.db).", file_path=db_path)

    _log_vocab_event(
        logger,
        "semantic.vocab.loaded",
        slug=slug,
        file_path=db_path,
        canon_count=len(vocab),
    )
    return vocab
