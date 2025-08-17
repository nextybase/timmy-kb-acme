# src/semantic/semantic_mapping.py
"""
Modulo per la gestione del file di mapping semantico nella pipeline Timmy-KB.

Refactor v1.0.4 (chirurgico):
- Normalizza il mapping in un formato canonico: dict[str, list[str]]
  Accetta varianti:
    - concept: [keywords...]
    - concept: { keywords: [...]}            # preferito
    - concept: { esempio: [...] }            # compat legacy (default_semantic_mapping.yaml)
- Validazione minima: dict non vuoto dopo normalizzazione
- Logging migliorato: conta concetti/keyword
"""

from pathlib import Path
from typing import Dict, List, Any
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import is_safe_subpath
from pipeline.exceptions import PipelineError, FileNotFoundError, ConfigError
from pipeline.constants import SEMANTIC_MAPPING_FILE
from pipeline.context import ClientContext

logger = get_structured_logger("semantic.mapping")


def _normalize_semantic_mapping(raw: Any) -> Dict[str, List[str]]:
    """
    Converte il mapping grezzo in un dizionario {concept: [keywords, ...]}.

    Regole:
    - Se il valore è una lista -> usala come keywords
    - Se è un dict -> prova 'keywords', poi 'esempio', poi 'tags'
    - Se è una stringa -> singola keyword
    - Dedup case-insensitive preservando l'ordine
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


def load_semantic_mapping(context: ClientContext, logger=None) -> Dict[str, List[str]]:
    """
    Carica e normalizza il mapping semantico per il cliente corrente.

    Returns:
        dict[str, list[str]]: mapping canonico {concept: [keywords...]}
    """
    logger = logger or get_structured_logger("semantic.mapping", context=context)

    mapping_path = context.config_dir / SEMANTIC_MAPPING_FILE
    if not is_safe_subpath(mapping_path, context.base_dir):
        raise PipelineError(
            f"Path mapping non sicuro: {mapping_path}",
            slug=context.slug,
            file_path=mapping_path,
        )

    if not mapping_path.exists():
        logger.error(
            f"📄 File di mapping semantico non trovato: {mapping_path}",
            extra={"slug": context.slug, "file_path": mapping_path},
        )
        raise FileNotFoundError(f"File mapping semantico non trovato: {mapping_path}")

    # 1) leggi mapping del cliente
    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        mapping = _normalize_semantic_mapping(raw)
        logger.info(
            f"📑 Mapping semantico caricato da {mapping_path}",
            extra={"slug": context.slug, "file_path": mapping_path, "concepts": len(mapping)},
        )
    except Exception as e:
        logger.error(
            f"❌ Errore lettura/parsing mapping {mapping_path}: {e}",
            extra={"slug": context.slug, "file_path": mapping_path},
        )
        raise PipelineError(f"Errore lettura mapping: {e}", slug=context.slug, file_path=mapping_path)

    # 2) fallback se vuoto/non valido
    if not mapping:
        logger.warning(
            "⚠️ Mapping semantico vuoto/non valido, carico fallback...",
            extra={"slug": context.slug, "file_path": mapping_path},
        )
        default_path = Path("config/default_semantic_mapping.yaml")
        if default_path.exists():
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                mapping = _normalize_semantic_mapping(raw)
                logger.info(
                    f"📑 Mapping di fallback caricato da {default_path}",
                    extra={"slug": context.slug, "file_path": default_path, "concepts": len(mapping)},
                )
            except Exception as e:
                logger.error(
                    f"❌ Errore caricamento mapping di fallback: {e}",
                    extra={"slug": context.slug, "file_path": default_path},
                )
                raise ConfigError(f"Errore caricamento mapping fallback: {e}", slug=context.slug, file_path=default_path)
        else:
            logger.error("❌ Mapping di fallback non trovato, impossibile continuare.", extra={"slug": context.slug})
            raise ConfigError("Mapping di fallback mancante.", slug=context.slug)

    return mapping
