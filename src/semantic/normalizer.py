# src/semantic/normalizer.py
"""
Modulo per normalizzare i tag proposti dall'auto_tagger sulla base delle regole
definite nel mapping cliente (semantic_mapping.yaml).

Scopo
-----
- Applicare sinonimi e canonicalizzazione (merge_into, drop, keep).
- Restituire un dizionario di candidati "puliti", pronto per la fase di review.
- Modulo puro: nessun I/O interattivo, nessun sys.exit().

Ordine di applicazione
----------------------
1. drop → elimina i tag presenti in stoplist/mapping.drop
2. merge_into → rimappa sinonimi a canonical
3. synonyms → arricchisce lista con sinonimi (facoltativo)
4. canonical → forza alias verso canonical definito
"""

from __future__ import annotations

from typing import Dict, Any, List


def normalize_tags(
    candidates: Dict[str, Dict[str, Any]], 
    mapping: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Applica regole di normalizzazione ai tag candidati.

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
      - dict con stessa struttura di candidates, ma con tags normalizzati
    """
    if not mapping:
        return candidates

    # Estrai regole dal mapping
    synonyms_map = (mapping.get("synonyms") or {}) if isinstance(mapping, dict) else {}
    canonical_map = (mapping.get("canonical") or {}) if isinstance(mapping, dict) else {}
    rules = (mapping.get("rules") or {}) if isinstance(mapping, dict) else {}
    drops = set((rules.get("drop") or []))

    merge_into_map = (rules.get("merge_into") or {})

    normed: Dict[str, Dict[str, Any]] = {}

    for rel_path, meta in candidates.items():
        tags: List[str] = list(meta.get("tags") or [])

        new_tags: List[str] = []
        for t in tags:
            tag = t.strip().lower()
            if not tag:
                continue

            # 1) drop
            if tag in drops:
                continue

            # 2) merge_into
            if tag in merge_into_map:
                tag = merge_into_map[tag]

            # 3) synonyms
            for canon, syns in synonyms_map.items():
                if tag in syns:
                    tag = canon
                    break

            # 4) canonical map
            if tag in canonical_map:
                tag = canonical_map[tag]

            new_tags.append(tag)

        # Dedup preservando ordine
        seen = set()
        final_tags = [t for t in new_tags if not (t in seen or seen.add(t))]

        normed[rel_path] = dict(meta)
        normed[rel_path]["tags"] = final_tags

    return normed
