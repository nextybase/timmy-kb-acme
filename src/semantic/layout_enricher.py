# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/layout_enricher.py
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple, cast

from pipeline.exceptions import ConfigError, ConversionError
from pipeline.path_utils import to_kebab

# ============================
# Types & Constraints Handling
# ============================


@dataclass(frozen=True)
class Constraints:
    """Vincoli obbligatori per l'arricchimento semantico.

    - max_depth: profondità massima consentita (root = 1).
    - allowed_prefixes: prefissi ammessi per i nodi top-level (kebab-case).
    - semantic_mapping: mappa canonico -> sinonimi/varianti per evitare duplicati.
    - max_nodes: limite massimo di nodi totali nella proposta generata.
    """

    max_depth: int
    allowed_prefixes: Tuple[str, ...]
    semantic_mapping: Dict[str, Tuple[str, ...]]
    max_nodes: int

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Constraints":
        try:
            md = int(d["max_depth"])
            mn = int(d["max_nodes"])
            ap_raw = d.get("allowed_prefixes", [])
            sm_raw = d.get("semantic_mapping", {})
        except (KeyError, TypeError, ValueError) as e:
            raise ConfigError("Constraints invalidi o incompleti") from e

        if not isinstance(ap_raw, Iterable):
            raise ConfigError("allowed_prefixes deve essere una lista/iterabile")
        if not isinstance(sm_raw, dict):
            raise ConfigError("semantic_mapping deve essere un dict")

        # normalizza i prefissi in kebab-case
        ap = tuple(sorted({to_kebab(str(x)) for x in ap_raw}))
        # normalizza la mappa semantica
        sm: Dict[str, Tuple[str, ...]] = {}
        for k, vals in sm_raw.items():
            canon = to_kebab(str(k))
            vs = tuple(sorted({to_kebab(str(v)) for v in (vals or [])}))
            sm[canon] = vs

        if md < 1:
            raise ConfigError("max_depth deve essere >= 1")
        if mn < 1:
            raise ConfigError("max_nodes deve essere >= 1")

        return Constraints(
            max_depth=md,
            allowed_prefixes=ap,
            semantic_mapping=sm,
            max_nodes=mn,
        )


# ============================
# Public API
# ============================


def suggest_layout(base_yaml: Dict[str, Any], vision_text: str, constraints: Dict[str, Any]) -> Dict[str, Any]:
    """Genera una proposta di struttura YAML (dict) coerente con il Vision Statement.

    - Funzione pura: nessun I/O, nessun accesso a rete o env.
    - Non modifica base_yaml: restituisce SOLO la proposta aggiuntiva.
    - Applica normalizzazione kebab-case, ordinamento deterministico,
      rispetto di max_depth, allowed_prefixes, semantic_mapping, max_nodes.

    Parametri:
      base_yaml: struttura di partenza (dict nested).
      vision_text: testo del Vision Statement estratto dal PDF (plain text).
      constraints: dict dei vincoli (obbligatorio).

    Ritorna:
      Dict rappresentante la proposta (solo nuovi rami). La UI eseguirà il merge.
    """
    c = Constraints.from_dict(constraints)

    # 1) Estrai termini chiave dal vision_text (approccio deterministico, rule-based)
    tokens = _extract_terms(vision_text)
    # 2) Mappa i token verso categorie canoniche note (semantic_mapping)
    topics = _map_tokens_to_topics(tokens, c.semantic_mapping)
    # 3) Filtra/normalizza i top-level rispetto ai prefissi ammessi
    top_level = _select_top_level_topics(topics, c.allowed_prefixes)

    # 4) Costruisci la proposta: per ogni top-level, crea nodi coerenti
    proposal: Dict[str, Any] = {}
    node_budget = c.max_nodes

    for top in top_level:
        if node_budget <= 0:
            break
        # Se già presente in base_yaml, evitiamo di duplicare il top-level;
        # la proposta aggiungerà solo sotto-sezioni mancanti.
        existing_branch = _get_branch(base_yaml, [top])
        proposed_branch, used = _build_branch(top, tokens, c, existing_branch=existing_branch)
        node_budget -= used
        if proposed_branch:
            # Merge shallow nel risultato (la UI farà il merge vero con base_yaml)
            proposal[top] = _sorted_dict(proposed_branch)

    # 5) Validazione schema + profondità + budget
    validate_yaml_schema(proposal, c.max_depth)
    _enforce_max_nodes(proposal, c.max_nodes)

    # 6) Ordinamento deterministico globale
    proposal = _sorted_dict(proposal)
    return proposal


def merge_non_distruttivo(base_yaml: Dict[str, Any], proposal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper per la UI: applica un merge non distruttivo.
    - preserva i nodi esistenti in base_yaml
    - aggiunge solo ciò che manca
    - in collisione semantica, aggiunge suffisso '-alt' al nodo proposto

    Ritorna la struttura risultante, ordinata in modo deterministico.
    """
    result = _deep_copy(base_yaml)
    _nd_merge_into(result, proposal)
    return _sorted_dict(result)


def validate_yaml_schema(tree: Dict[str, Any], max_depth: int) -> None:
    """
    Valida che:
    - il tree sia un dict annidato
    - le chiavi siano stringhe kebab-case non vuote
    - la profondità non superi max_depth
    """
    if not isinstance(tree, dict):
        raise ConversionError("La struttura deve essere un dict")
    _validate_node(tree, depth=1, max_depth=max_depth)


def _extract_terms(text: str, min_len: int = 4, top_k: int = 24) -> List[str]:
    """
    Estrae termini semplici dal testo:
    - tokenizzazione banale
    - filtra parole corte/stop-words basilari
    - ritorna i top_k più frequenti (kebab-case)
    """
    if not text:
        return []

    stop = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "your",
        "una",
        "uno",
        "gli",
        "nei",
        "nelle",
        "delle",
        "degli",
        "per",
        "con",
        "del",
        "della",
        "dello",
        "dei",
        "il",
        "lo",
        "la",
        "le",
        "un",
        "di",
        "da",
        "in",
        "su",
        "tra",
        "fra",
        "come",
        "anche",
        "non",
        "che",
        "sono",
        "è",
        "e",
        "a",
        "al",
        "ai",
        "agli",
    }
    # split su non-ltr
    raw = re.split(r"[^A-Za-zÀ-ÖØ-öø-ÿ0-9_]+", text)
    toks = [to_kebab(t) for t in raw if t]
    toks = [t for t in toks if len(t) >= min_len and t not in stop]
    freq = Counter(toks)
    return [w for w, _ in freq.most_common(top_k)]


def _map_tokens_to_topics(tokens: List[str], semantic_map: Dict[str, Tuple[str, ...]]) -> List[str]:
    """Mappa i token a categorie canoniche usando semantic_map.

    Se un token corrisponde a canonico o a un suo sinonimo, associa al canonico. Mantiene l'ordine
    per frequenza d'apparizione (approssimata).
    """
    if not tokens:
        return []

    inv_index: Dict[str, str] = {}
    for canon, syns in semantic_map.items():
        inv_index[canon] = canon
        for s in syns:
            inv_index[s] = canon

    mapped: List[str] = []
    seen = set()
    for token in tokens:
        maybe_canon = inv_index.get(token)
        if maybe_canon and maybe_canon not in seen:
            mapped.append(maybe_canon)
            seen.add(maybe_canon)
    return mapped


def _select_top_level_topics(topics: List[str], allowed_prefixes: Tuple[str, ...]) -> List[str]:
    """Se allowed_prefixes è non vuoto, filtra i topics per prefisso ammesso.

    Altrimenti, restituisce i topics così come sono.
    """
    if not allowed_prefixes:
        return topics
    allowed = set(allowed_prefixes)
    return [t for t in topics if _first_token(t) in allowed]


def _first_token(kebab: str) -> str:
    return kebab.split("-", 1)[0] if kebab else ""


def _get_branch(tree: Dict[str, Any], path: List[str]) -> Dict[str, Any] | None:
    """Recupera il sotto-dizionario alla path (se esiste ed è dict), altrimenti None."""
    cur: Any = tree
    for k in path:
        if not (isinstance(cur, dict) and k in cur):
            return None
        cur = cur[k]
    return cur if isinstance(cur, dict) else None


def _build_branch(
    top: str,
    tokens: List[str],
    c: Constraints,
    *,
    existing_branch: Dict[str, Any] | None,
) -> Tuple[Dict[str, Any], int]:
    """
    Costruisce un sotto-albero per il nodo top-level:
    - Ricava 3-6 sotto-nodi coerenti (deterministici) a partire dai token affini.
    - Evita duplicati con existing_branch (se presente).
    - Rispetta max_depth e max_nodes (ritorna anche quanti nodi ha usato).
    """
    used_nodes = 0
    branch: Dict[str, Any] = {}
    existing_children = set(existing_branch.keys()) if isinstance(existing_branch, dict) else set()

    # Sottotemi: prendi token che iniziano con lo stesso prefisso principale o che contengono il top
    # (approccio conservativo e deterministico, senza ML).
    subtokens = [t for t in tokens if t != top and (top in t or _first_token(t) == _first_token(top))]
    # Rendi un set ordinato deterministico
    candidates = []
    seen = set()
    for t in subtokens:
        k = to_kebab(t)
        if k and k not in seen:
            seen.add(k)
            candidates.append(k)

    # Limita sottotemi per non esplodere (3..6)
    min_children, max_children = 3, 6
    children = candidates[:max_children]
    if len(children) < min_children:
        raise ConversionError(f"Struttura insufficiente per '{top}': figli={len(children)}/{min_children}")

    # Crea nodi foglia (dict vuoti) rispettando max_depth (top=1, figli=2)
    for child in children:
        child_name = to_kebab(child)
        # riduci il nome a seconda del contesto (evita ripetizione del top)
        if child_name.startswith(f"{top}-"):
            child_name = child_name[len(top) + 1 :]
        # niente override se già esiste in base
        if child_name in existing_children:
            continue
        branch[child_name] = {}  # foglia
        used_nodes += 1
        if used_nodes >= (c.max_nodes - 1):  # -1 per contare il top nel budget globale chiamante
            break

    # trim in base a budget residuo
    return branch, used_nodes


def _validate_node(node: Dict[str, Any], *, depth: int, max_depth: int) -> None:
    if depth > max_depth:
        raise ConversionError(f"Profondità massima superata: {depth} > {max_depth}")
    for k, v in node.items():
        if not isinstance(k, str) or not k:
            raise ConversionError("Chiave non valida (stringa vuota o non stringa)")
        if to_kebab(k) != k:
            raise ConversionError(f"Chiave non normalizzata (kebab-case richiesto): {k!r}")
        if not isinstance(v, dict):
            raise ConversionError(f"Valore non valido per chiave {k!r}: atteso dict")
        _validate_node(v, depth=depth + 1, max_depth=max_depth)


def _enforce_max_nodes(tree: Dict[str, Any], max_nodes: int) -> None:
    """Garantisce che il numero totale di nodi (dict) non superi max_nodes."""
    count = _count_nodes(tree)
    if count <= max_nodes:
        return

    # Taglio non distruttivo ma deterministico: rimuove chiavi in eccesso partendo dalle foglie.
    def prune(d: Dict[str, Any]) -> None:
        nonlocal count
        if count <= max_nodes:
            return
        # Visita prima i figli (profondità), poi eventualmente elimina la chiave corrente
        for k in list(d.keys()):
            if count <= max_nodes:
                break
            v = d.get(k)
            if isinstance(v, dict) and v:
                prune(v)
            if count > max_nodes and k in d:
                # Rimuovi il nodo corrente (foglia o ramo già potato)
                del d[k]
                count -= 1

    prune(tree)


def _count_nodes(tree: Dict[str, Any]) -> int:
    total = 0
    stack = [tree]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            total += len(cur)
            for v in cur.values():
                if isinstance(v, dict):
                    stack.append(v)
    return total


def _nd_merge_into(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    """
    Merge non distruttivo in-place:
    - se una chiave non esiste in dst: copia
    - se esiste ed è dict: ricorsivo
    - se esiste ed è conflitto (non dict): error hard-fail
    """
    for k, v in src.items():
        if k not in dst:
            dst[k] = _deep_copy(v)
        else:
            if isinstance(dst[k], dict) and isinstance(v, dict):
                _nd_merge_into(dst[k], v)
            else:
                raise ConversionError(f"Conflitto merge su chiave '{k}'")


def _sorted_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Ritorna un nuovo dict ordinato lessicograficamente sulle chiavi, applicato ricorsivamente per
    stabilità Git."""
    out: Dict[str, Any] = {}
    for k in sorted(d.keys()):
        v = d[k]
        out[k] = _sorted_dict(v) if isinstance(v, dict) else v
    return out


def _deep_copy(d: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(d, dict):
        return cast(Dict[str, Any], d)
    out: Dict[str, Any] = {}
    for k, v in d.items():
        out[k] = _deep_copy(v) if isinstance(v, dict) else v
    return out
