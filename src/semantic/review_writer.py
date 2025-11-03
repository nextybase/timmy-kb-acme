# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/review_writer.py
"""Generatore dello stub di revisione dei tag.

Scopo
-----
Dato un dizionario di candidati (già normalizzati), crea un file
`semantic/tags_reviewed.yaml` che il revisore umano può aprire e
completare. Lo stub propone tutti i tag unici trovati nei documenti,
con azione di default `keep`, e include esempi di occorrenza.

Formato YAML generato (esempio)
-------------------------------
context:
  generated_at: "2025-08-25T12:34:56Z"
  total_documents: 12
  total_unique_tags: 37

review:
  - name: "ai"
    action: "keep"           # keep | drop | merge_into:<canonical>
    synonyms: []             # eventuali sinonimi che vuoi mantenere
    note: ""                 # spazio per chiarimenti
    examples:                # dove l'abbiamo trovato (subset)
      - "raw/organizzazione/piano_ai.pdf"
      - "raw/glossario/ai_definizioni.pdf"

documents:                   # (comodo per audit)
  "raw/organizzazione/piano_ai.pdf":
    tags: ["ai", "organizzazione"]

Note
----
- Modulo puro: nessun input() o sys.exit().
- Se il file esiste e `overwrite=False`, non viene sovrascritto.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, cast

from pipeline.exceptions import ConfigError  # <- coerenza contract errori
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within

yaml_module: Any | None = None
try:
    import yaml as _yaml

    yaml_module = _yaml
except Exception:  # pragma: no cover
    yaml_module = None  # degradazione controllata: il chiamante pu? gestire l'assenza


def _now_utc_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _unique_tags_with_examples(candidates: Dict[str, Dict[str, Any]], max_examples: int = 5) -> Dict[str, List[str]]:
    """Estrae l'insieme dei tag unici dal corpus e un piccolo campione di documenti in cui ciascun
    tag compare (per aiutare la revisione)."""
    tag_examples: Dict[str, List[str]] = {}
    for rel_path, meta in candidates.items():
        tags = list(meta.get("tags") or [])
        for t in tags:
            tag = str(t).strip().lower()
            if not tag:
                continue
            lst = tag_examples.setdefault(tag, [])
            if len(lst) < max_examples:
                lst.append(rel_path)
    return tag_examples


def write_review_stub(
    candidates_norm: Dict[str, Dict[str, Any]],
    yaml_path: Path,
    *,
    overwrite: bool = False,
) -> None:
    """Scrive lo stub `tags_reviewed.yaml`.

    Parametri:
      - candidates_norm: dict dei candidati normalizzati (relative_path -> meta)
      - yaml_path: destinazione del file YAML
      - overwrite: se False e il file esiste, non fa nulla
    """
    if yaml_module is None:
        # Cambio: ConfigError al posto di RuntimeError per coerenza con orchestratori/EXIT_CODES
        raise ConfigError(
            "PyYAML non disponibile: impossibile scrivere lo YAML di review.",
            file_path=str(yaml_path),
        )

    yaml_path = Path(yaml_path).resolve()
    # Path-safety forte: yaml_path deve stare sotto la propria directory madre
    ensure_within(yaml_path.parent, yaml_path)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    if yaml_path.exists() and not overwrite:
        # Non sovrascrivere per sicurezza: il revisore potrebbe aver lavorato su questo file
        return

    # 1) calcola tag unici + esempi di occorrenza
    tag_examples = _unique_tags_with_examples(candidates_norm, max_examples=5)
    unique_tags: List[str] = sorted(tag_examples.keys())

    # 2) sezione review (lista di item editabili dall'umano)
    review_items: List[Dict[str, Any]] = []
    for tag in unique_tags:
        review_items.append(
            {
                "name": tag,
                "action": "keep",  # keep | drop | merge_into:<canonical>
                "synonyms": [],  # puoi popolare qui sinonimi utili
                "note": "",
                "examples": tag_examples[tag],
            }
        )

    # 3) sezione documents (utile per audit e per creare filtri during-review)
    documents: Dict[str, Dict[str, List[str]]] = {}
    for rel_path, meta in sorted(candidates_norm.items()):
        tags = [str(t).strip().lower() for t in (meta.get("tags") or []) if str(t).strip()]
        documents[rel_path] = {"tags": tags}

    data = {
        "context": {
            "generated_at": _now_utc_iso(),
            "total_documents": len(candidates_norm),
            "total_unique_tags": len(unique_tags),
        },
        "review": review_items,
        "documents": documents,
    }

    # Dump su buffer e commit atomico
    yaml_api = cast(Any, yaml_module)
    payload = yaml_api.safe_dump(data, allow_unicode=True, sort_keys=False)
    safe_write_text(yaml_path, payload, encoding="utf-8", atomic=True)
