# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/semantic_mapping.py
"""Fase 2 — Arricchimento semantico (consuma tags_reviewed).

Modulo per la gestione del file di mapping semantico nella pipeline Timmy-KB.

Refactor v1.0.5 (Blocco B):
- Path-safety STRONG: validazione con `ensure_within(...)` sia per il mapping cliente
  che per il fallback.
- Fallback sicuro: `context.repo_root_dir / "config" / "default_semantic_mapping.yaml"`.
- Logger: nessun logger a livello di modulo; viene creato dentro le funzioni.
- Normalizzazione mapping robusta (compat con varianti legacy).

Formato normalizzato: dict[str, list[str]]
  Accetta varianti:
    - concept: [keywords...]
    - concept: { keywords: [...]}            # preferito
    - concept: { tags: [...] }               # fallback generico
    - concept: 'keyword'
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from pipeline.constants import SEMANTIC_MAPPING_FILE
from pipeline.exceptions import ConfigError, PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within

__all__ = ["load_semantic_mapping"]

TAG_PATTERN = re.compile(r"[a-z0-9\-]{3,}")
KEYWORD_PATTERN = TAG_PATTERN  # legacy alias (da rimuovere dopo migrazione completa)


class _Ctx(Protocol):
    config_dir: Optional[Path]
    repo_root_dir: Optional[Path]
    slug: Optional[str]


def _normalize_semantic_mapping(raw: Any) -> Dict[str, List[str]]:
    """Converte il mapping grezzo in un dizionario {concept: [keywords, ...]}.

    Regole:
    - Se il valore e' una lista -> usala come keywords
    - Se e' un dict -> prova 'keywords', poi 'tags'
    - Se e' una stringa -> singola keyword
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


def _has_phase1_keywords(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    for payload in raw.values():
        if isinstance(payload, dict) and "keywords" in payload:
            return True
    return False


def load_semantic_mapping(context: _Ctx, logger: Optional[logging.Logger] = None) -> Dict[str, List[str]]:
    """Carica e normalizza il mapping semantico per il cliente corrente.

    Restituisce:
        dict[str, list[str]]: mapping canonico {concept: [keywords...]}
    """
    logger = logger or get_structured_logger("semantic.mapping", context=context)

    # 0) Preferisci mapping cliente in config_dir/semantic_mapping.yaml (workspace)
    try:
        from pipeline.yaml_utils import yaml_read as _yaml_read_ws

        cfg_dir = getattr(context, "config_dir", None)
        if cfg_dir is not None:
            cfg_dir_p = Path(cfg_dir)
            candidate = cfg_dir_p / SEMANTIC_MAPPING_FILE
            ensure_within(cfg_dir_p, candidate)
            raw_ws = _yaml_read_ws(cfg_dir_p, candidate) or {}
            if _has_phase1_keywords(raw_ws):
                raise ConfigError(
                    "Uso scorretto: 'keywords' non appartiene a semantic_mapping.yaml (Fase 1). "
                    "Usa semantic/tags_reviewed.yaml (Fase 2).",
                    file_path=str(candidate),
                    slug=context.slug,
                )
            mapping_ws = _normalize_semantic_mapping(raw_ws)
            if mapping_ws:
                logger.info(
                    "Mapping semantico caricato (workspace)",
                    extra={"slug": context.slug, "file_path": str(candidate), "concepts": len(mapping_ws)},
                )
                return mapping_ws
    except Exception:
        logger.info(
            "Mapping cliente non disponibile in config/, provo fallback",
            extra={"slug": getattr(context, "slug", None)},
        )

    repo_root = getattr(context, "repo_root_dir", None)
    if repo_root is None:
        raise PipelineError("Contesto incompleto: repo_root_dir mancante", slug=context.slug)
    mapping_path = repo_root / "semantic" / SEMANTIC_MAPPING_FILE
    try:
        ensure_within(repo_root, mapping_path)  # STRONG guard
    except ConfigError as e:
        raise PipelineError(
            f"Path mapping non sicuro: {mapping_path}",
            slug=context.slug,
            file_path=mapping_path,
        ) from e

    try:
        from pipeline.yaml_utils import yaml_read

        raw = yaml_read(mapping_path.parent, mapping_path) or {}
        if _has_phase1_keywords(raw):
            raise ConfigError(
                "Uso scorretto: 'keywords' non appartiene a semantic_mapping.yaml (Fase 1). "
                "Usa semantic/tags_reviewed.yaml (Fase 2).",
                file_path=str(mapping_path),
                slug=context.slug,
            )
        mapping = _normalize_semantic_mapping(raw)
        logger.info(
            "📑 Mapping semantico caricato",
            extra={
                "slug": context.slug,
                "file_path": str(mapping_path),
                "concepts": len(mapping),
            },
        )
    except Exception as e:
        logger.info(
            "Mapping client non disponibile, uso fallback repo default",
            extra={"slug": context.slug, "file_path": str(mapping_path), "error": str(e)},
        )
        repo_mapping_dir = Path(repo_root) / "config"
        fallback_path = repo_mapping_dir / "default_semantic_mapping.yaml"
        try:
            ensure_within(repo_mapping_dir, fallback_path)
        except ConfigError as exc:
            raise PipelineError(
                "Fallback mapping fuori dal perimetro consentito",
                slug=context.slug,
                file_path=fallback_path,
            ) from exc
        from pipeline.yaml_utils import yaml_read

        raw = yaml_read(repo_mapping_dir, fallback_path) or {}
        if _has_phase1_keywords(raw):
            raise ConfigError(
                "Uso scorretto: 'keywords' non appartiene a semantic_mapping.yaml (Fase 1). "
                "Usa semantic/tags_reviewed.yaml (Fase 2).",
                file_path=str(fallback_path),
                slug=context.slug,
            )
        mapping = _normalize_semantic_mapping(raw)
        logger.info(
            "📑 Mapping semantico di fallback caricato",
            extra={
                "slug": context.slug,
                "file_path": str(fallback_path),
                "concepts": len(mapping),
            },
        )

    if not mapping:
        logger.warning(
            "⚠️ Mapping semantico vuoto/non valido", extra={"slug": context.slug, "file_path": str(mapping_path)}
        )
        return {}

    return mapping
    # 3) fallback se vuoto/non valido
    if not mapping:
        logger.warning(
            "âš ï ̧ Mapping semantico vuoto/non valido; carico fallback",
            extra={"slug": context.slug, "file_path": str(mapping_path)},
        )
        # Risoluzione sicura del fallback rispetto alla root del repo
        repo_root_fallback = getattr(context, "repo_root_dir", None) or Path(__file__).resolve().parents[2]
        repo_config_dir = Path(repo_root_fallback) / "config"
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
                from pipeline.yaml_utils import yaml_read

                raw = yaml_read(repo_config_dir, default_path) or {}
                mapping = _normalize_semantic_mapping(raw)
                logger.info(
                    "ðŸ“‘ Mapping di fallback caricato",
                    extra={
                        "slug": context.slug,
                        "file_path": str(default_path),
                        "concepts": len(mapping),
                    },
                )
            except Exception as e:
                logger.error(
                    f"âŒ Errore caricamento mapping di fallback: {e}",
                    extra={"slug": context.slug, "file_path": str(default_path)},
                )
                raise ConfigError(
                    f"Errore caricamento mapping fallback: {e}",
                    slug=context.slug,
                    file_path=str(default_path),
                )
        else:
            logger.error(
                "âŒ Mapping di fallback non trovato; impossibile continuare.",
                extra={"slug": context.slug, "file_path": str(default_path)},
            )
            raise ConfigError(
                "Mapping di fallback mancante.",
                slug=context.slug,
                file_path=str(default_path),
            )

    return mapping
