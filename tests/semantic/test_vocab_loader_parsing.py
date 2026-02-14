# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pipeline.exceptions import ConfigError
from semantic import vocab_loader as vl


@pytest.fixture(autouse=True)
def _non_strict_for_tooling_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    # I test in questo modulo verificano la compatibilita' di parsing
    # delle tooling shapes. In strict non sono ammesse.
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")


FIXTURE_INPUTS: dict[str, Any] = {
    "simple": {"Alpha": ["a1", "a2"]},
    "storage": {
        "tags": [
            {"name": "Up", "synonyms": ["U", "u"]},
            {"name": "Down", "action": "merge_into:Up", "synonyms": ["D"]},
            {"name": "Left", "synonyms": ["L"]},
            {"name": "left", "synonyms": ["l2"]},
        ]
    },
    "sequence": [
        ["Alpha", "a1"],
        ["Alpha", "a2"],
        {"canonical": "Gamma", "alias": "g1"},
    ],
}

REFERENCE_VOCAB_OUTPUTS: dict[str, dict[str, dict[str, list[str]]]] = {
    "simple": {
        "alpha": {
            "aliases": ["a1", "a2"],
        },
    },
    "storage": {
        "Left": {
            "aliases": ["L", "l2"],
        },
        "Up": {
            "aliases": ["U", "Down", "D"],
        },
    },
    "sequence": {
        "alpha": {
            "aliases": ["a1", "a2"],
        },
        "gamma": {
            "aliases": ["g1"],
        },
    },
}


def _aliases_for(vocab: Mapping[str, Mapping[str, list[str]]], canonical: str) -> list[str]:
    for key, payload in vocab.items():
        if key.casefold() == canonical.casefold():
            return payload["aliases"]
    raise KeyError(canonical)


def _normalize_for_comparison(vocab: Mapping[str, Mapping[str, list[str]]]) -> dict[str, tuple[str, ...]]:
    return {canon: tuple(sorted(payload["aliases"])) for canon, payload in vocab.items()}


def _to_vocab_reference_pre_refactor(data: Any) -> dict[str, dict[str, list[str]]]:
    out: dict[str, list[str]] = defaultdict(list)
    seen_aliases: dict[str, set[str]] = defaultdict(set)

    def _append_alias(canon_value: Any, alias_value: Any) -> None:
        canon = str(canon_value).strip().casefold()
        alias = str(alias_value).strip()
        if not canon or not alias:
            return
        alias_key = alias.casefold()
        if alias_key in seen_aliases[canon]:
            return
        seen_aliases[canon].add(alias_key)
        out[canon].append(alias)

    def _build_from_tag_rows(rows: Sequence[Any]) -> dict[str, dict[str, list[str]]]:
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
                vl._safe_structured_warning(
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
                        vl._safe_structured_warning(
                            "semantic.vocab.canonical_case_conflict",
                            extra={
                                "canonical_norm": target_norm,
                                "canonical": existing_target,
                                "canonical_new": target_raw,
                            },
                        )
                    display_names.setdefault(target_norm, target_raw)

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

    def _raise_invalid() -> None:
        raise ConfigError("Canonical vocab shape invalid")

    if isinstance(data, Mapping):
        sample_val = next(iter(data.values()), None)
        if isinstance(sample_val, Mapping) and "aliases" in sample_val:
            result: dict[str, dict[str, list[str]]] = {}
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
                _raise_invalid()
            return result

        items = cast(Any, data).get("tags") if hasattr(data, "get") else None
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
            processed = _build_from_tag_rows(items)
            if processed:
                return processed
            _raise_invalid()

        try:
            for canon, aliases in cast(Mapping[str, Iterable[Any]], data).items():
                if isinstance(aliases, (str, bytes)):
                    _append_alias(canon, aliases)
                else:
                    for a in aliases:
                        _append_alias(canon, a)
            if out:
                return {k: {"aliases": v} for k, v in out.items()}
            _raise_invalid()
        except Exception:
            _raise_invalid()

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

    _raise_invalid()
    return {}


def test_aliases_are_preserved_across_formats() -> None:
    simple_vocab = vl._to_vocab(FIXTURE_INPUTS["simple"])
    sequence_vocab = vl._to_vocab(FIXTURE_INPUTS["sequence"])
    storage_vocab = vl._to_vocab(FIXTURE_INPUTS["storage"])

    assert _aliases_for(simple_vocab, "Alpha") == REFERENCE_VOCAB_OUTPUTS["simple"]["alpha"]["aliases"]
    assert _aliases_for(sequence_vocab, "Alpha") == REFERENCE_VOCAB_OUTPUTS["sequence"]["alpha"]["aliases"]
    assert _aliases_for(sequence_vocab, "Gamma") == REFERENCE_VOCAB_OUTPUTS["sequence"]["gamma"]["aliases"]
    assert _aliases_for(storage_vocab, "Left") == REFERENCE_VOCAB_OUTPUTS["storage"]["Left"]["aliases"]
    assert set(_aliases_for(storage_vocab, "Up")) == set(REFERENCE_VOCAB_OUTPUTS["storage"]["Up"]["aliases"])


def test_canonical_case_conflict_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    data = {
        "tags": [
            {"name": "Rome"},
            {"name": "rome"},
        ]
    }
    vl._to_vocab(data)
    assert any(rec.getMessage() == "semantic.vocab.canonical_case_conflict" for rec in caplog.records)


def test_merge_chain_preserves_aliases() -> None:
    data = {
        "tags": [
            {"name": "A", "action": "merge_into:B", "synonyms": ["a"]},
            {"name": "B", "action": "merge_into:C", "synonyms": ["b"]},
            {"name": "C", "synonyms": ["c"]},
        ]
    }
    vocab = vl._to_vocab(data)
    assert set(vocab) == {"C"}
    alias_lower = {alias.casefold() for alias in vocab["C"]["aliases"]}
    assert alias_lower >= {"a", "b", "c"}


@pytest.mark.parametrize(
    "aliases",
    [
        ["Spot", "spot", "Spot"],
        ["Spot", "spot", "spot"],
    ],
)
def test_alias_dedup_case_insensitive(aliases: list[str]) -> None:
    result = vl._to_vocab({"Spot": aliases})
    assert _aliases_for(result, "Spot") == ["Spot"]


@pytest.mark.parametrize("fixture_name", list(REFERENCE_VOCAB_OUTPUTS.keys()))
def test_refactor_preserves_reference_vocab_outputs(fixture_name: str) -> None:
    data = FIXTURE_INPUTS[fixture_name]
    expected = REFERENCE_VOCAB_OUTPUTS[fixture_name]
    actual = vl._to_vocab(data)
    assert _normalize_for_comparison(actual) == _normalize_for_comparison(expected)


@given(
    st.lists(
        st.tuples(
            st.text(min_size=1, max_size=12),
            st.text(min_size=1, max_size=12),
        ),
        min_size=1,
        max_size=200,
    )
)
def test_to_vocab_casefold_dedup_property(rows: list[tuple[str, str]]) -> None:
    data: dict[str, list[str]] = defaultdict(list)
    for canon, alias in rows:
        data[canon].append(alias)

    vocab = vl._to_vocab(data)
    for payload in vocab.values():
        aliases = payload["aliases"]
        lowered = [value.casefold() for value in aliases]
        assert len(lowered) == len(set(lowered))
