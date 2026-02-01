# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/spacy_extractor.py
"""Estrattore keyword basato su SpaCy con mapping aree da semantic_mapping.yaml.

Obiettivo: leggere il testo dei PDF in raw/, estrarre termini e frasi chiave,
collegarli alle aree definite nel mapping e restituire candidati per tags_raw.csv.

"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, iter_safe_paths
from pipeline.workspace_layout import WorkspaceLayout

from .config import SemanticConfig
from .lexicon import LexiconEntry, build_lexicon

LOGGER = get_structured_logger("semantic.spacy_extractor")

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _read_markdown_text(md_path: Path, *, layout: WorkspaceLayout) -> str:
    """
    Legge il contenuto di un file Markdown e lo restituisce come stringa.
    """
    md_path = md_path.expanduser().resolve()
    if not md_path.is_file():
        raise FileNotFoundError(f"Markdown non trovato: {md_path}")
    safe_md = cast(Path, ensure_within_and_resolve(layout.normalized_dir, md_path))
    with safe_md.open("r", encoding="utf-8") as handle:
        return handle.read()


def _load_spacy(model_name: str) -> Any:
    try:
        import spacy
    except Exception as exc:  # pragma: no cover
        raise ConfigError("SpaCy non disponibile: impossibile attivare il backend NLP.") from exc

    try:
        return spacy.load(model_name)
    except OSError as exc:  # pragma: no cover
        # Modello non installato
        raise ConfigError(f"Modello SpaCy '{model_name}' non disponibile.") from exc
    except Exception as exc:  # pragma: no cover
        raise ConfigError("Errore nel caricamento di SpaCy.") from exc


@lru_cache(maxsize=2)
def _get_nlp(model_name: str) -> Any:
    """Restituisce (con cache) il modello SpaCy richiesto."""
    return _load_spacy(model_name)


def _collect_phrases(doc: Any, limit: int) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Restituisce noun-chunks (lemmi) e entita' (testo, label), con limite soft."""
    noun_chunks: List[str] = []
    entities: List[Tuple[str, str]] = []
    try:
        for chunk in doc.noun_chunks:
            if len(noun_chunks) >= limit:
                break
            lemma = chunk.lemma_.strip().lower()
            text = chunk.text.strip()
            if lemma:
                noun_chunks.append(lemma)
            elif text:
                noun_chunks.append(text.lower())
    except Exception:
        noun_chunks = []
    try:
        for ent in doc.ents:
            txt = ent.text.strip()
            lbl = ent.label_.strip()
            if txt:
                entities.append((txt, lbl))
    except Exception:
        entities = []
    return noun_chunks, entities


def _build_phrase_matcher(nlp: Any, lexicon: Iterable[LexiconEntry]) -> Tuple[Any, Dict[int, Tuple[str, str]]]:
    """Crea un matcher SpaCy con termini -> (area, entity)."""
    try:
        from spacy.matcher import PhraseMatcher
    except Exception as exc:  # pragma: no cover
        raise ConfigError("SpaCy matcher non disponibile.") from exc

    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    label_map: Dict[int, Tuple[str, str]] = {}
    for entry in lexicon:
        label = f"{entry.area_key}::{entry.entity_id}"
        label_id = nlp.vocab.strings[label]
        patterns = [nlp.make_doc(term) for term in entry.terms if term]
        if not patterns:
            continue
        matcher.add(label, patterns)
        label_map[label_id] = (entry.area_key, entry.entity_id)
    return matcher, label_map


def _score_matches(
    matches: Iterable[Tuple[int, int, int]] | Any,
    doc: Any,
    label_map: Dict[int, Tuple[str, str]],
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, List[str]]]]:
    """Aggrega conteggi per area/entity con evidenze."""
    scores: Dict[str, Dict[str, float]] = {}
    evidences: Dict[str, Dict[str, List[str]]] = {}
    for match_id, start, end in matches:
        ref = label_map.get(match_id)
        if not ref:
            continue
        area, entity = ref
        span = doc[start:end]
        scores.setdefault(area, {})
        evidences.setdefault(area, {})
        scores[area][entity] = scores[area].get(entity, 0.0) + 1.0
        evidences[area].setdefault(entity, []).append(span.text)
    return scores, evidences


def _prune(
    scores: Dict[str, Dict[str, float]],
    evidences: Dict[str, Dict[str, List[str]]],
    top_k: int,
) -> Tuple[List[str], Dict[str, float], Dict[str, Any]]:
    """Seleziona le top entita' per area (fino a top_k globali) e prepara metadata."""
    collected: List[Tuple[str, str, float]] = []
    for area, entities in scores.items():
        for ent, score in entities.items():
            collected.append((area, ent, score))
    collected.sort(key=lambda item: (-item[2], item[0], item[1]))
    selected = collected[: max(1, int(top_k))]

    tags: List[str] = []
    score_map: Dict[str, float] = {}
    source_meta: Dict[str, Any] = {"spacy": {"areas": {}, "evidences": evidences}}

    for area, ent, score in selected:
        if ent not in tags:
            tags.append(ent)
        score_map[f"{area}:{ent}"] = score
        source_meta["spacy"]["areas"].setdefault(area, []).append(ent)
    return tags, score_map, source_meta


# --------------------------------------------------------------------------------------
# API principale
# --------------------------------------------------------------------------------------


def extract_spacy_tags(
    normalized_dir: Path,
    cfg: SemanticConfig,
    *,
    model_name: str = "it_core_news_sm",
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Estrae candidati tag dai documenti (Markdown derivati da raw/) usando SpaCy, mappandoli alle aree.

    Ritorna un dict: relative_path -> {tags, entities, keyphrases, score, sources}
    """
    layout = WorkspaceLayout.from_workspace(cfg.repo_root_dir)
    normalized_dir = layout.normalized_dir
    lexicon = build_lexicon(cfg.mapping)
    if not lexicon:
        return {}

    try:
        nlp = _get_nlp(model_name)
        matcher, label_map = _build_phrase_matcher(nlp, lexicon)
    except Exception as exc:
        err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
        err_type = type(exc).__name__
        raise ConfigError(f"SpaCy fallito (model={model_name}).") from exc

    candidates: Dict[str, Dict[str, Any]] = {}
    for md_path in iter_safe_paths(
        normalized_dir,
        include_dirs=False,
        include_files=True,
        suffixes=(".md",),
    ):
        try:
            rel_path = md_path.relative_to(normalized_dir).as_posix()
        except Exception:
            continue
        try:
            text = _read_markdown_text(md_path, layout=layout)
        except FileNotFoundError as exc:
            raise ConfigError(
                f"Markdown non trovato per il documento {md_path.name}: esegui raw_ingest.",
                file_path=str(md_path),
            ) from exc
        except Exception as exc:
            err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
            err_type = type(exc).__name__
            raise ConfigError(
                f"Markdown non leggibile per {md_path.name}: {err_type}: {err_line}",
                file_path=str(md_path),
            ) from exc
        if not text:
            continue

        doc = nlp(text)
        matches = matcher(doc)
        scores, evidences = _score_matches(matches, doc, label_map)
        tags, score_map, source_meta = _prune(scores, evidences, cfg.top_k)
        noun_chunks, entities = _collect_phrases(doc, cfg.top_k)

        candidates[rel_path] = {
            "tags": tags,
            "entities": [{"text": t, "label": lbl} for t, lbl in entities],
            "keyphrases": noun_chunks,
            "score": score_map,
            "sources": source_meta,
        }

    return candidates
