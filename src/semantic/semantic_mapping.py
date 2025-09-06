# src/semantic/semantic_mapping.py
"""
Modulo per la gestione del file di mapping semantico nella pipeline Timmy-KB.

Refactor v1.0.5 (Blocco B):
- Path-safety STRONG: validazione con `ensure_within(...)` sia per il mapping cliente
  che per il fallback.
- Fallback sicuro: il default è risolto rispetto a `context.repo_root_dir / "config" / "default_semantic_mapping.yaml"`.
- Logger: nessun logger a livello di modulo; viene creato dentro le funzioni.
- Normalizzazione mapping robusta (compat con varianti legacy).

Formato normalizzato: dict[str, list[str]]
  Accetta varianti:
    - concept: [keywords...]
    - concept: { keywords: [...]}            # preferito
    - concept: { esempio: [...] }            # compat legacy (default_semantic_mapping.yaml)
    - concept: { tags: [...] }               # fallback generico
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Protocol

import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within
from pipeline.exceptions import PipelineError, ConfigError
from pipeline.constants import SEMANTIC_MAPPING_FILE

__all__ = ["load_semantic_mapping"]


class _Ctx(Protocol):
    config_dir: Optional[Path]
    repo_root_dir: Optional[Path]
    slug: Optional[str]


def _normalize_semantic_mapping(raw: Any) -> Dict[str, List[str]]:
    """
    Converte il mapping grezzo in un dizionario {concept: [keywords, ...]}.

    Regole:
    - Se il valore è una lista -> usala come keywords
    - Se è un dict -> prova 'keywords', poi 'esempio', poi 'tags'
    - Se è una stringa -> singola keyword
    - Dedup case-insensitive preservando l'ordine (mantiene il casing originale)
    """
    norm: Dict[str, List[str]] = {}
    if not isinstance(raw, dict):
        return norm

    for concept, payload in raw.items():
        kws: List[str] = []
        if isinstance(payload, dict):
            src = None
            if isinstance(payload.get("keywords"), list):
                src = payload.get("keywords")
            elif isinstance(payload.get("esempio"), list):  # compat con YAML attuale
                src = payload.get("esempio")
            elif isinstance(payload.get("tags"), list):
                src = payload.get("tags")
            if src:
                kws = [str(x) for x in src if isinstance(x, (str, int, float))]
        elif isinstance(payload, list):
            kws = [str(x) for x in payload if isinstance(x, (str, int, float))]
        elif isinstance(payload, str):
            kws = [payload]

        # normalizza/filtra
        kws = [k.strip() for k in kws if str(k).strip()]
        seen = set()
        dedup: List[str] = []
        for k in kws:
            kl = k.lower()
            if kl not in seen:
                seen.add(kl)
                dedup.append(k)
        if dedup:
            norm[str(concept)] = dedup

    return norm


def load_semantic_mapping(
    context: _Ctx, logger: Optional[logging.Logger] = None
) -> Dict[str, List[str]]:
    """
    Carica e normalizza il mapping semantico per il cliente corrente.

    Restituisce:
        dict[str, list[str]]: mapping canonico {concept: [keywords...]}
    """
    logger = logger or get_structured_logger("semantic.mapping", context=context)

    # 1) mapping specifico del cliente (sotto sandbox)
    if context.config_dir is None:
        raise PipelineError("Contesto incompleto: config_dir mancante", slug=context.slug)
    mapping_path = context.config_dir / SEMANTIC_MAPPING_FILE
    try:
        ensure_within(context.config_dir, mapping_path)  # STRONG guard
    except ConfigError as e:
        raise PipelineError(
            f"Path mapping non sicuro: {mapping_path}",
            slug=context.slug,
            file_path=mapping_path,
        ) from e

    if not mapping_path.exists():
        logger.error(
            "📄 File di mapping semantico non trovato",
            extra={"slug": context.slug, "file_path": str(mapping_path)},
        )
        # Coerenza contract errori: usare ConfigError (no built-in)
        raise ConfigError(
            f"File mapping semantico non trovato: {mapping_path}",
            slug=context.slug,
            file_path=str(mapping_path),
        )

    # 2) leggi mapping del cliente
    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        mapping = _normalize_semantic_mapping(raw)
        logger.info(
            "📑 Mapping semantico caricato",
            extra={"slug": context.slug, "file_path": str(mapping_path), "concepts": len(mapping)},
        )
    except Exception as e:
        logger.error(
            f"❌ Errore lettura/parsing mapping: {e}",
            extra={"slug": context.slug, "file_path": str(mapping_path)},
        )
        raise PipelineError(
            f"Errore lettura mapping: {e}", slug=context.slug, file_path=mapping_path
        )

    # 3) fallback se vuoto/non valido
    if not mapping:
        logger.warning(
            "⚠️ Mapping semantico vuoto/non valido; carico fallback",
            extra={"slug": context.slug, "file_path": str(mapping_path)},
        )
        # Risoluzione sicura del fallback rispetto alla root del repo
        repo_root: Path = (
            getattr(context, "repo_root_dir", None) or Path(__file__).resolve().parents[2]
        )
        repo_config_dir = repo_root / "config"
        default_path = repo_config_dir / "default_semantic_mapping.yaml"
        try:
            ensure_within(repo_config_dir, default_path)  # STRONG guard sul fallback
        except ConfigError as e:
            raise ConfigError(
                "Mapping di fallback fuori dalla repo root configurata.",
                slug=context.slug,
                file_path=str(default_path),
            ) from e

        if default_path.exists():
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                mapping = _normalize_semantic_mapping(raw)
                logger.info(
                    "📑 Mapping di fallback caricato",
                    extra={
                        "slug": context.slug,
                        "file_path": str(default_path),
                        "concepts": len(mapping),
                    },
                )
            except Exception as e:
                logger.error(
                    f"❌ Errore caricamento mapping di fallback: {e}",
                    extra={"slug": context.slug, "file_path": str(default_path)},
                )
                raise ConfigError(
                    f"Errore caricamento mapping fallback: {e}",
                    slug=context.slug,
                    file_path=str(default_path),
                )
        else:
            logger.error(
                "❌ Mapping di fallback non trovato; impossibile continuare.",
                extra={"slug": context.slug, "file_path": str(default_path)},
            )
            raise ConfigError(
                "Mapping di fallback mancante.", slug=context.slug, file_path=str(default_path)
            )

    return mapping
