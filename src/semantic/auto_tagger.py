# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/auto_tagger.py
"""
MVP: generatore di candidati semantici basato su euristiche (path/filename).

Caratteristiche
---------------
- Nessuna dipendenza esterna: funziona anche senza modelli (NER/embeddings).
- Estrae tag da:
  1) segmenti di percorso (cartelle significative sotto RAW)
  2) nome file (tokenizzazione su separatori comuni)
- Applica stoplist/limiti dal `SemanticConfig` (lang, top_k, score_min, stop_tags).
- Restituisce un dict per documento + writer CSV pronto all'uso.

Output CSV (columns)
--------------------
relative_path | suggested_tags | entities | keyphrases | score | sources

Dove:
- suggested_tags: lista di tag (comma-separated, lowercase)
- entities, keyphrases: vuote in MVP (riempite nelle fasi successive)
- score: somma pesata per tag (semplice)
- sources: JSON con evidenze {"path":[...], "filename":[...]}

Nota: modulo “puro” (niente input()/sys.exit()). La scrittura CSV è **atomica**
(`safe_write_text`) e path-safe (guardie `ensure_within`).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, iter_safe_pdfs
from pipeline.tracing import start_decision_span

from .config import SemanticConfig

__all__ = [
    "extract_semantic_candidates",
    "render_tags_csv",
]

LOGGER = get_structured_logger("semantic.auto_tagger")

# ------------------------------ helpers base --------------------------------- #

_SPLIT_RE = re.compile(r"[^\w]+", flags=re.UNICODE)  # split su non-alfanumerici
_NUMERIC_ONLY_RE = re.compile(r"^\d+$")


def _is_meaningful_token(tok: str) -> bool:
    """Scarta token banali: vuoti, puramente numerici, molto corti."""
    if not tok:
        return False
    if _NUMERIC_ONLY_RE.match(tok):
        return False
    if len(tok) < 2:
        return False
    return True


def _tokenize_filename(name: str) -> list[str]:
    """Tokenizza il nome file (senza estensione) in lowercase."""
    base = name.rsplit(".", 1)[0]
    toks = [t.strip().lower() for t in _SPLIT_RE.split(base)]
    return [t for t in toks if _is_meaningful_token(t)]


def _path_segments(rel_from_raw: Path) -> list[str]:
    """Estrae segmenti di cartella (lowercase) dal path relativo alla RAW."""
    parts = [p.strip().lower() for p in rel_from_raw.parent.as_posix().split("/") if p.strip()]
    return [p for p in parts if _is_meaningful_token(p)]


def _score_and_rank(
    path_tags: Iterable[str],
    file_tags: Iterable[str],
    *,
    stop: Iterable[str],
    top_k: int,
) -> tuple[list[str], dict[str, float]]:
    """Combina tag da path e filename con uno scoring semplicissimo (path > filename).

    - path: peso 1.0
    - filename: peso 0.6
    Deduplica preservando l'ordine di “forza” (path prima).
    """
    stopset = set(s.strip().lower() for s in (stop or []) if s)
    weights: dict[str, float] = {}

    ordered: list[tuple[str, float]] = []

    def add_tokens(tokens: Iterable[str], weight: float) -> None:
        for token in tokens:
            t = token.strip().lower()
            if not t or t in stopset:
                continue
            if t not in weights:
                weights[t] = 0.0
                ordered.append((t, weight))
            weights[t] += weight

    add_tokens(path_tags, 1.0)
    add_tokens(file_tags, 0.6)

    order_index = {tag: index for index, (tag, _) in enumerate(ordered)}
    ranked = sorted(weights.items(), key=lambda item: (-item[1], order_index[item[0]]))

    tags = [tag for tag, _ in ranked[: max(1, int(top_k))]]
    return tags, weights


def _iter_pdf_files(raw_dir: Path) -> Iterable[Path]:
    """Itera tutti i PDF sotto la RAW, ricorsivamente, in ordine deterministico."""
    if not raw_dir.exists():
        return

    def _on_skip(candidate: Path, reason: str) -> None:
        if reason == "symlink":
            LOGGER.warning("semantic.auto_tagger.skip_symlink", extra={"file_path": str(candidate)})
        else:
            LOGGER.warning(
                "semantic.auto_tagger.skip_unsafe",
                extra={"file_path": str(candidate), "error": reason},
            )

    yield from iter_safe_pdfs(raw_dir, on_skip=_on_skip)


# ------------------------------ API principali ------------------------------- #


def _extract_semantic_candidates_heuristic(raw_dir: Path, cfg: SemanticConfig) -> dict[str, dict[str, Any]]:
    """Genera candidati dai PDF sotto `raw_dir` usando euristiche path/filename."""
    raw_dir = Path(raw_dir).resolve()
    base_dir = Path(cfg.base_dir).resolve()

    # STRONG guard: RAW deve essere sotto la sandbox del cliente
    ensure_within(base_dir, raw_dir)

    candidates: dict[str, dict[str, Any]] = {}

    for pdf_path in _iter_pdf_files(raw_dir):
        try:
            rel_from_base = pdf_path.relative_to(base_dir)
        except ValueError:
            # se per qualche motivo non è sotto base_dir, fallback a path relativo da RAW
            rel_from_base = pdf_path.relative_to(raw_dir)

        rel_str = rel_from_base.as_posix()

        path_tags = _path_segments(pdf_path.relative_to(raw_dir))
        file_tags = _tokenize_filename(pdf_path.name)

        suggested, weights = _score_and_rank(
            path_tags,
            file_tags,
            stop=cfg.stop_tags,
            top_k=cfg.top_k,
        )

        # In MVP non calcoliamo score_min per singolo tag; manteniamo i pesi grezzi.
        candidates[rel_str] = {
            "tags": suggested,
            "entities": [],
            "keyphrases": [],
            "score": weights,
            "sources": {"path": path_tags, "filename": file_tags},
        }

    return candidates


def _merge_spacy_candidates(
    base_candidates: dict[str, dict[str, Any]],
    spacy_candidates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Unisce i risultati SpaCy con le euristiche (union + somma pesi)."""
    if not spacy_candidates:
        return base_candidates

    merged = dict(base_candidates)
    for rel_path, spacy_meta in spacy_candidates.items():
        target = merged.setdefault(
            rel_path,
            {"tags": [], "entities": [], "keyphrases": [], "score": {}, "sources": {}},
        )

        existing_tags = [str(t).strip() for t in target.get("tags") or [] if str(t).strip()]
        spacy_tags = [str(t).strip() for t in spacy_meta.get("tags") or [] if str(t).strip()]
        tags_seen = {t.lower() for t in existing_tags}
        for tag in spacy_tags:
            if tag.lower() not in tags_seen:
                existing_tags.append(tag)
                tags_seen.add(tag.lower())
        target["tags"] = existing_tags

        existing_entities = list(target.get("entities") or [])
        existing_entities.extend(spacy_meta.get("entities") or [])
        target["entities"] = existing_entities

        keyphrases = list(target.get("keyphrases") or [])
        for kp in spacy_meta.get("keyphrases") or []:
            if kp not in keyphrases:
                keyphrases.append(kp)
        target["keyphrases"] = keyphrases

        score = dict(target.get("score") or {})
        for tag, val in (spacy_meta.get("score") or {}).items():
            try:
                score[tag] = float(score.get(tag, 0.0)) + float(val)
            except Exception:
                continue
        target["score"] = score

        sources = dict(target.get("sources") or {})
        spacy_source = spacy_meta.get("sources") or {}
        if spacy_source:
            sources["spacy"] = spacy_source.get("spacy", spacy_source)
        target["sources"] = sources
    return merged


def extract_semantic_candidates(raw_dir: Path, cfg: SemanticConfig) -> dict[str, dict[str, Any]]:
    """Genera candidati dai PDF sotto `raw_dir` usando euristiche path/filename e opzionalmente SpaCy."""
    candidates = _extract_semantic_candidates_heuristic(raw_dir, cfg)

    backend_env = os.getenv("TAGS_NLP_BACKEND", cfg.nlp_backend).strip().lower()
    if backend_env == "spacy":
        try:
            from semantic.spacy_extractor import extract_spacy_tags

            spacy_candidates = extract_spacy_tags(
                raw_dir,
                cfg,
                model_name=os.getenv("SPACY_MODEL", cfg.spacy_model),
                logger=LOGGER,
            )
            candidates = _merge_spacy_candidates(candidates, spacy_candidates)
            if spacy_candidates:
                with start_decision_span(
                    "semantic_classification",
                    slug=None,
                    run_id=None,
                    trace_kind="onboarding",
                    phase="semantic.auto_tagger",
                    attributes={
                        "decision_type": "semantic_classification",
                        "dataset_area": getattr(cfg.mapping, "name", None),
                        "model_version": os.getenv("SPACY_MODEL", cfg.spacy_model),
                        "status": "success",
                    },
                ):
                    LOGGER.info(
                        "semantic.auto_tagger.spacy_used",
                        extra={"count": len(spacy_candidates)},
                    )
        except Exception as exc:
            LOGGER.warning(
                "semantic.auto_tagger.spacy_failed",
                extra={"error": str(exc)},
            )
    return candidates


def render_tags_csv(
    candidates: Mapping[str, Mapping[str, Any]],
    csv_path: Path,
    *,
    base_dir: Path,
) -> None:
    """Scrive `tags_raw.csv` (esteso) con colonne: relative_path | suggested_tags | entities |
    keyphrases | score | sources.

    Note:
    - Scrittura **atomica** tramite buffer + `safe_write_text(..., atomic=True)`.
    - Ordine deterministico per riga (`sorted(candidates.items())`).
    - JSON serializzati con `sort_keys=True` per stabilizzare il diff.
    """
    # Path-safety forte: risolvi entro il perimetro base e verifica parent
    safe_csv_path = ensure_within_and_resolve(base_dir, csv_path)
    safe_csv_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_within(safe_csv_path.parent, safe_csv_path)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["relative_path", "suggested_tags", "entities", "keyphrases", "score", "sources"])

    for rel_path, meta in sorted(candidates.items()):
        tags = [str(tag).strip().lower() for tag in (meta.get("tags") or []) if str(tag).strip()]
        ents = meta.get("entities") or []
        keys = meta.get("keyphrases") or []
        score = meta.get("score") or {}
        sources = meta.get("sources") or {}

        writer.writerow(
            [
                rel_path,
                ", ".join(tags),
                json.dumps(ents, ensure_ascii=False),
                json.dumps(keys, ensure_ascii=False),
                json.dumps(score, ensure_ascii=False, sort_keys=True),
                json.dumps(sources, ensure_ascii=False, sort_keys=True),
            ]
        )

    safe_write_text(safe_csv_path, buf.getvalue(), encoding="utf-8", atomic=True)
