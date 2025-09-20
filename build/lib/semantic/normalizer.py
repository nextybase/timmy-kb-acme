# src/semantic/normalizer.py
"""Modulo per normalizzare i tag proposti dall'auto_tagger sulla base delle regole definite nel
mapping cliente (semantic_mapping.yaml).

Scopo
-----
- Applicare sinonimi e canonicalizzazione (merge_into, drop, keep).
- Restituire un dizionario di candidati "puliti", pronto per la fase di review.
- Modulo puro: nessun I/O interattivo, nessun sys.exit().

Ordine di applicazione
----------------------
1. drop → elimina i tag presenti in stoplist/mapping.rules.drop
2. merge_into → rimappa sinonimi/alias verso un target
3. synonyms → se il tag corrisponde a un sinonimo, sostituisce con il canonico
4. canonical → forza alias verso canonical definito

Note d’implementazione
----------------------
- Tutti i confronti sono case-insensitive: normalizziamo a lowercase sia chiavi sia valori.
- `synonyms` accetta sia lista che singolo valore: viene coerzionato a lista di stringhe lower.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def _to_lc(s: Any) -> str:
    """Converte qualunque valore a stringa normalizzata lowercase/trim, vuota se None/''."""
    if s is None:
        return ""
    return str(s).strip().lower()


def _coerce_list_str(x: Any) -> List[str]:
    """Coercizza a lista di stringhe lowercase/trim, filtrando i vuoti."""
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        it = x
    else:
        it = [x]
    out: List[str] = []
    for v in it:
        lv = _to_lc(v)
        if lv:
            out.append(lv)
    return out


def _normalize_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Restituisce una vista normalizzata (lowercase) delle sezioni rilevanti del mapping."""
    # Sezioni top-level (possono mancare)
    synonyms_raw = mapping.get("synonyms") or {}
    canonical_raw = mapping.get("canonical") or {}
    rules_raw = mapping.get("rules") or {}

    # synonyms: {canonical: [syn1, syn2, ...]} (coercizione prudente)
    synonyms_map: Dict[str, List[str]] = {}
    if isinstance(synonyms_raw, Mapping):
        for canon, syns in synonyms_raw.items():
            canon_l = _to_lc(canon)
            if not canon_l:
                continue
            synonyms_map[canon_l] = _coerce_list_str(syns)

    # canonical: {alias: canonical}
    canonical_map: Dict[str, str] = {}
    if isinstance(canonical_raw, Mapping):
        for alias, canon in canonical_raw.items():
            alias_l = _to_lc(alias)
            canon_l = _to_lc(canon)
            if alias_l and canon_l:
                canonical_map[alias_l] = canon_l

    # rules.drop: [tag1, tag2, ...]
    drops_set = set(_coerce_list_str(rules_raw.get("drop")) if isinstance(rules_raw, Mapping) else [])

    # rules.merge_into: {alias: target}
    merge_into_map: Dict[str, str] = {}
    if isinstance(rules_raw, Mapping):
        mi_raw = rules_raw.get("merge_into") or {}
        if isinstance(mi_raw, Mapping):
            for alias, target in mi_raw.items():
                alias_l = _to_lc(alias)
                target_l = _to_lc(target)
                if alias_l and target_l:
                    merge_into_map[alias_l] = target_l

    return {
        "synonyms": synonyms_map,
        "canonical": canonical_map,
        "drops": drops_set,
        "merge_into": merge_into_map,
    }


def _apply_synonyms(tag: str, synonyms_map: Mapping[str, Iterable[str]]) -> str:
    """Se `tag` è presente tra i sinonimi di un canonico, ritorna il canonico, altrimenti il tag
    stesso."""
    for canon, syns in synonyms_map.items():
        # syns è già lower/trim
        if tag in syns:
            return canon
    return tag


def normalize_tags(
    candidates: Dict[str, Dict[str, Any]],
    mapping: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Applica regole di normalizzazione ai tag candidati.

    Parametri:
      - candidates: dict del tipo {
            "relative/path/to.pdf": {
                "tags": [...],
                "entities": [...],
                "keyphrases": [...],
                ...
            }, ...
        }
      - mapping: dict cliente-specifico caricato da semantic_mapping.yaml

    Ritorna:
      - dict con stessa struttura di candidates, ma con tags normalizzati (lowercase, deduplicati).
    """
    if not mapping:
        return candidates

    m = _normalize_mapping(mapping)
    synonyms_map: Mapping[str, Iterable[str]] = m["synonyms"]
    canonical_map: Mapping[str, str] = m["canonical"]
    drops: set[str] = m["drops"]
    merge_into_map: Mapping[str, str] = m["merge_into"]

    normed: Dict[str, Dict[str, Any]] = {}

    for rel_path, meta in candidates.items():
        tags: List[str] = list(meta.get("tags") or [])
        new_tags: List[str] = []

        for t in tags:
            tag = _to_lc(t)
            if not tag:
                continue

            # 1) drop
            if tag in drops:
                continue

            # 2) merge_into (alias -> target canonicalizzato)
            if tag in merge_into_map:
                tag = merge_into_map[tag]

            # 3) synonyms (se il tag è un sinonimo di qualche canonico)
            tag = _apply_synonyms(tag, synonyms_map)

            # 4) canonical map (alias diretto -> canonical)
            if tag in canonical_map:
                tag = canonical_map[tag]

            new_tags.append(tag)

        # dedup preservando ordine (senza usare side-effect in comprensione)
        seen: set[str] = set()
        final_tags: List[str] = []
        for t in new_tags:
            if t not in seen:
                seen.add(t)
                final_tags.append(t)

        # copia meta e sostituisci i tag normalizzati
        out_meta = dict(meta)
        out_meta["tags"] = final_tags
        normed[rel_path] = out_meta

    return normed
