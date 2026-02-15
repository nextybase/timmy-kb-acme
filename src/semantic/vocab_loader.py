# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/vocab_loader.py
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Set, cast

import pipeline.path_utils as ppath  # late-bound per testability
from pipeline.beta_flags import is_beta_strict
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger

__all__ = ["load_reviewed_vocab", "load_tags_db_vocab"]

LOGGER = get_structured_logger("semantic.vocab_loader")
_FALLBACK_LOG = get_structured_logger("semantic.vocab_loader.fallback")


def _safe_structured_warning(event: str, *, extra: Mapping[str, Any]) -> None:
    """Emette un warning strutturato senza degradazione silenziosa.

    Se il logger strutturato fallisce (handler/extra non serializzabile), degrada su stdlib logger.
    """
    try:
        LOGGER.warning(event, extra=dict(extra))
    except Exception as exc:
        # Fallback non silenzioso: stdlib logger con contesto minimizzato.
        _FALLBACK_LOG.warning(
            "structured_logger_failed",
            extra={"event": event, "error": repr(exc), "payload_keys": list(extra.keys())},
            exc_info=True,
        )
        _FALLBACK_LOG.warning(event, extra={"payload": dict(extra)})


def _load_tags_db_or_raise() -> Any:
    try:  # pragma: no cover - dipende dall'ambiente
        from storage.tags_store import load_tags_db as _load_tags_db
    except Exception as exc:  # pragma: no cover
        _safe_structured_warning("semantic.vocab.loader_missing", extra={"error": str(exc)})
        raise ConfigError("tags.db missing or unreadable") from exc
    return _load_tags_db


def _normalize_vocab_result(canon_map: Mapping[str, Iterable[str]]) -> Dict[str, Dict[str, list[str]]]:
    """Ordina e de-duplica alias preservando l'ordine d'inserimento."""
    result: Dict[str, Dict[str, list[str]]] = {}
    for canon, aliases in canon_map.items():
        canon_key = str(canon)
        ordered: list[str] = []
        seen: set[str] = set()
        for alias in aliases or []:
            alias_str = str(alias)
            if not alias_str or alias_str in seen:
                continue
            seen.add(alias_str)
            ordered.append(alias_str)
        if ordered:
            result[canon_key] = {"aliases": ordered}
    return result


def _append_alias(
    storage: Dict[str, list[str]],
    seen_aliases: Dict[str, Set[str]],
    canon_value: Any,
    alias_value: Any,
) -> None:
    canon = str(canon_value).strip().casefold()
    alias = str(alias_value).strip()
    if not canon or not alias:
        return
    alias_key = alias.casefold()
    if alias_key in seen_aliases[canon]:
        return
    seen_aliases[canon].add(alias_key)
    storage[canon].append(alias)


def _parse_normalized_vocab_mapping(data: Mapping[str, Any]) -> Dict[str, Dict[str, list[str]]] | None:
    sample_val = next(iter(data.values()), None)
    if not (isinstance(sample_val, Mapping) and "aliases" in sample_val):
        return None
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
    if not result:
        return None
    return result


def _parse_simple_vocab_mapping(data: Mapping[str, Iterable[Any]]) -> Dict[str, Dict[str, list[str]]] | None:
    out: Dict[str, list[str]] = defaultdict(list)
    seen_aliases: Dict[str, Set[str]] = defaultdict(set)
    for canon, aliases in data.items():
        if isinstance(aliases, (str, bytes)):
            _append_alias(out, seen_aliases, canon, aliases)
        else:
            for alias in aliases:
                _append_alias(out, seen_aliases, canon, alias)
    return _normalize_vocab_result(out) if out else None


def _parse_sequence_rows(rows: Sequence[Any]) -> Dict[str, Dict[str, list[str]]] | None:
    out: Dict[str, list[str]] = defaultdict(list)
    seen_aliases: Dict[str, Set[str]] = defaultdict(set)
    for row in rows:
        if isinstance(row, Mapping):
            canon = row.get("canonical") or row.get("canon") or row.get("c") or ""
            alias = row.get("alias") or row.get("a") or ""
            _append_alias(out, seen_aliases, canon, alias)
        elif isinstance(row, (tuple, list)) and len(row) >= 2:
            _append_alias(out, seen_aliases, row[0], row[1])
    return _normalize_vocab_result(out) if out else None


def _parse_storage_tags_rows(rows: Sequence[Any]) -> Dict[str, Dict[str, list[str]]] | None:
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
        max_hops = 256
        while max_hops > 0:
            next_target = merge_map.get(current)
            if not next_target or next_target in visited:
                break
            visited.add(current)
            current = next_target
            max_hops -= 1
        if max_hops == 0:
            raise ConfigError("Canonical vocab merge chain too deep")
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
            _safe_structured_warning(
                "semantic.vocab.canonical_case_conflict",
                extra={
                    "canonical_norm": name,
                    "canonical": existing_display,
                    "canonical_new": raw_name,
                },
            )
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
                    _safe_structured_warning(
                        "semantic.vocab.canonical_case_conflict",
                        extra={
                            "canonical_norm": target_norm,
                            "canonical": existing_target,
                            "canonical_new": target_raw,
                        },
                    )
                display_names.setdefault(target_norm, target_raw)

    for canon in sorted(synonym_map):
        aliases = synonym_map[canon]
        for alias in aliases:
            alias_norm = alias.casefold()
            if alias_norm in synonym_map and alias_norm != canon and alias_norm not in merge_map:
                merge_map[alias_norm] = canon

    all_names = sorted(set(synonym_map.keys()) | set(merge_map.keys()) | set(merge_map.values()))
    for name in all_names:
        target = _resolve_target(name)
        if not target:
            continue
        _ensure_target(target)
        if name != target:
            _add_final_alias(target, display_names.get(name, name))
        for alias in synonym_map.get(name, []):
            _add_final_alias(target, alias)

    if not final_aliases:
        return None
    return {display_names.get(canon, canon): {"aliases": aliases} for canon, aliases in final_aliases.items()}


def _to_vocab(data: Any) -> Dict[str, Dict[str, list[str]]]:
    """
    Normalizza data in: { canonical: { "aliases": [str,...] } } mantenendo l'ordine di inserimento.

    Formati accettati:
    - gia normalizzato: Dict[str, Dict[str, Iterable[str]]]
    - mapping semplice: Dict[str, Iterable[str]]  (canonical -> aliases)
    - formato storage: {"tags": [{"name": str, "action": str, "synonyms": [str,...]}, ...]}
    - lista di dict:   [{"canonical": str, "alias": str}, ...]
    - lista di tuple:  [(canonical:str, alias:str), ...]
    - lista di liste:  [[canonical, alias], ...]
    - altro/non riconosciuto -> ConfigError
    """

    def _raise_invalid() -> None:
        raise ConfigError("Canonical vocab shape invalid")

    def _tooling_shape_guard(shape: str) -> None:
        """
        Tooling shapes (simple_mapping, sequence_rows) sono ammessi solo
        fuori dalla modalita strict (Envelope runtime).
        """
        if is_beta_strict():
            raise ConfigError(f"Canonical vocab tooling shape not allowed in strict mode: {shape}")
        _safe_structured_warning(
            "semantic.vocab.tooling_shape_accepted",
            extra={"shape": shape},
        )

    if isinstance(data, Mapping):
        normalized = _parse_normalized_vocab_mapping(cast(Mapping[str, Any], data))
        if normalized:
            LOGGER.info("semantic.vocab.shape_detected", extra={"shape": "normalized_mapping"})
            return normalized

        has_storage_key = hasattr(data, "keys") and "tags" in cast(Mapping[str, Any], data).keys()
        items = cast(Any, data).get("tags") if hasattr(data, "get") else None
        if has_storage_key:
            if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
                _raise_invalid()
            parsed_storage = _parse_storage_tags_rows(items)
            if parsed_storage:
                LOGGER.info("semantic.vocab.shape_detected", extra={"shape": "storage_tags"})
                return parsed_storage
            # Se il payload dichiara shape storage (`tags`) ma non contiene righe utili,
            # la shape e' invalida: non tentare fallback su mapping "semplice".
            _raise_invalid()

        simple = _parse_simple_vocab_mapping(cast(Mapping[str, Iterable[Any]], data))
        if simple:
            LOGGER.info("semantic.vocab.shape_detected", extra={"shape": "simple_mapping"})
            _tooling_shape_guard("simple_mapping")
            return simple
        _raise_invalid()

    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        parsed_sequence = _parse_sequence_rows(data)
        if parsed_sequence:
            LOGGER.info("semantic.vocab.shape_detected", extra={"shape": "sequence_rows"})
            _tooling_shape_guard("sequence_rows")
            return parsed_sequence

    _raise_invalid()
    return {}


def load_tags_db_vocab(db_path: Path) -> Dict[str, Dict[str, list[str]]]:
    """
    Wrapper patchabile che carica i 'canonici' da tags.db e li adatta alla shape attesa.

    Se il loader non e disponibile o il DB e illeggibile -> ConfigError (fail-fast).
    """
    try:
        loader = _load_tags_db_or_raise()
        raw = loader(str(db_path))  # accetta str/Path
    except Exception as exc:  # errori SQLite (query/cursor)
        _safe_structured_warning(
            "semantic.vocab.load_failed",
            extra={"file_path": str(db_path), "error": str(exc)},
        )
        raise ConfigError("tags.db missing or unreadable", file_path=str(db_path)) from exc
    try:
        return _to_vocab(raw)
    except ConfigError as exc:
        raise ConfigError(str(exc), file_path=str(db_path)) from exc
    except Exception as exc:
        raise ConfigError("Canonical vocab shape invalid", file_path=str(db_path)) from exc


def _semantic_dir(repo_root_dir: Path) -> Path:
    return repo_root_dir / "semantic"


def _log_vocab_event(
    logger: logging.Logger,
    event: str,
    *,
    slug: str | None = None,
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
    repo_root_dir: Path,
    logger: logging.Logger,
    *,
    slug: str | None = None,
) -> Dict[str, Dict[str, list[str]]]:
    """Get reviewed vocab from tags.db (SSoT)."""
    repo_root_dir = Path(repo_root_dir)
    perimeter_root = repo_root_dir
    sem_dir = ppath.ensure_within_and_resolve(perimeter_root, _semantic_dir(repo_root_dir))
    db_path = ppath.ensure_within_and_resolve(sem_dir, sem_dir / "tags.db")
    if not db_path.exists() or not db_path.is_file():
        _log_vocab_event(
            logger,
            "semantic.vocab.db_missing",
            slug=slug,
            file_path=db_path,
            canon_count=0,
        )
        raise ConfigError("tags.db missing or unreadable", file_path=str(db_path))

    vocab = load_tags_db_vocab(db_path)
    if not vocab:
        _log_vocab_event(
            logger,
            "semantic.vocab.db_empty",
            slug=slug,
            file_path=db_path,
            canon_count=0,
        )
        raise ConfigError("Canonical vocab shape invalid", file_path=str(db_path))

    _log_vocab_event(
        logger,
        "semantic.vocab.loaded",
        slug=slug,
        file_path=db_path,
        canon_count=len(vocab),
    )
    return vocab
