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
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within
from .config import SemanticConfig

__all__ = [
    "extract_semantic_candidates",
    "render_tags_csv",
]

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


def _tokenize_filename(name: str) -> List[str]:
    """Tokenizza il nome file (senza estensione) in lowercase."""
    base = name.rsplit(".", 1)[0]
    toks = [t.strip().lower() for t in _SPLIT_RE.split(base)]
    return [t for t in toks if _is_meaningful_token(t)]


def _path_segments(rel_from_raw: Path) -> List[str]:
    """Estrae segmenti di cartella (lowercase) dal path relativo alla RAW."""
    parts = [p.strip().lower() for p in rel_from_raw.parent.as_posix().split("/") if p.strip()]
    return [p for p in parts if _is_meaningful_token(p)]


def _score_and_rank(
    path_tags: Iterable[str],
    file_tags: Iterable[str],
    *,
    stop: Iterable[str],
    top_k: int,
) -> Tuple[List[str], Dict[str, float]]:
    """
    Combina tag da path e filename con uno scoring semplicissimo (path > filename).
    - path: peso 1.0
    - filename: peso 0.6
    Deduplica preservando l'ordine di “forza” (path prima).
    """
    stopset = set(s.strip().lower() for s in (stop or []) if s)
    weights: Dict[str, float] = {}

    ordered: List[Tuple[str, float]] = []

    def add_tokens(tokens: Iterable[str], w: float):
        for t in tokens:
            t = t.strip().lower()
            if not t or t in stopset:
                continue
            if t not in weights:
                weights[t] = 0.0
                ordered.append((t, w))
            weights[t] += w

    add_tokens(path_tags, 1.0)
    add_tokens(file_tags, 0.6)

    # Ordina per peso desc, poi per ordine di comparsa (tie-break deterministico)
    order_index = {t: i for i, (t, _) in enumerate(ordered)}
    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], order_index[kv[0]]))

    tags = [t for t, _ in ranked[: max(1, int(top_k))]]
    return tags, weights


def _iter_pdf_files(raw_dir: Path) -> Iterable[Path]:
    """Itera tutti i PDF sotto la RAW, ricorsivamente, in ordine deterministico."""
    if not raw_dir.exists():
        return []
    yield from sorted(raw_dir.rglob("*.pdf"), key=lambda p: p.as_posix().lower())


# ------------------------------ API principali ------------------------------- #

def extract_semantic_candidates(raw_dir: Path, cfg: SemanticConfig) -> Dict[str, Dict[str, Any]]:
    """
    Genera candidati dai PDF sotto `raw_dir` usando euristiche path/filename.

    Ritorna:
      {
        "relative/path/to.pdf": {
          "tags": [...],
          "entities": [],     # MVP
          "keyphrases": [],   # MVP
          "score": {"tag": float, ...},   # pesi grezzi
          "sources": {"path":[...], "filename":[...]},
        },
        ...
      }
    """
    raw_dir = Path(raw_dir).resolve()
    base_dir = Path(cfg.base_dir).resolve()

    # STRONG guard: RAW deve essere sotto la sandbox del cliente
    ensure_within(base_dir, raw_dir)

    candidates: Dict[str, Dict[str, Any]] = {}

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


def render_tags_csv(candidates: Dict[str, Dict[str, Any]], csv_path: Path) -> None:
    """
    Scrive `tags_raw.csv` (esteso) con colonne:
      relative_path | suggested_tags | entities | keyphrases | score | sources

    Note:
    - Scrittura **atomica** tramite buffer + `safe_write_text(..., atomic=True)`.
    - Ordine deterministico per riga (`sorted(candidates.items())`).
    - JSON serializzati con `sort_keys=True` per stabilizzare il diff.
    """
    csv_path = Path(csv_path).resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_within(csv_path.parent, csv_path)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["relative_path", "suggested_tags", "entities", "keyphrases", "score", "sources"])

    for rel_path, meta in sorted(candidates.items()):
        tags = [str(t).strip().lower() for t in (meta.get("tags") or []) if str(t).strip()]
        ents = meta.get("entities") or []
        keys = meta.get("keyphrases") or []
        score = meta.get("score") or {}
        sources = meta.get("sources") or {}

        writer.writerow([
            rel_path,
            ", ".join(tags),
            json.dumps(ents, ensure_ascii=False),
            json.dumps(keys, ensure_ascii=False),
            json.dumps(score, ensure_ascii=False, sort_keys=True),
            json.dumps(sources, ensure_ascii=False, sort_keys=True),
        ])

    safe_write_text(csv_path, buf.getvalue(), encoding="utf-8", atomic=True)
