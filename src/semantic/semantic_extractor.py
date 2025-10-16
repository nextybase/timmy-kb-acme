# src/semantic/semantic_extractor.py
"""Fase 2 - Arricchimento semantico
--------------------------------
I 'keywords' (sinonimi/trigger di tagging) NON provengono piu da
semantic_mapping.yaml / cartelle_raw.yaml (Fase 1).
Si leggono da: base_dir/semantic/tags_reviewed.yaml

Compatibilita test: riesponiamo `load_semantic_mapping(...)` come shim
in modo che i test possano monkeypatcharlo. Di default legge da
`tags_reviewed.yaml`.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import yaml

from pipeline.exceptions import InputDirectoryMissing, PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, is_safe_subpath, read_text_safe


class _Ctx(Protocol):
    base_dir: Path
    md_dir: Path
    slug: Optional[str]
    config_dir: Optional[Path]
    repo_root_dir: Optional[Path]


def _list_markdown_files(context: _Ctx, logger: Optional[logging.Logger] = None) -> List[Path]:
    logger = logger or get_structured_logger("semantic.files", context=context)

    if getattr(context, "md_dir", None) is None or getattr(context, "base_dir", None) is None:
        raise PipelineError(
            "Contesto incompleto: md_dir/base_dir mancanti",
            slug=getattr(context, "slug", None),
        )

    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PipelineError("Path non sicuro", slug=context.slug, file_path=context.md_dir)

    if not context.md_dir.exists() or not context.md_dir.is_dir():
        raise InputDirectoryMissing(f"Directory markdown non valida: {context.md_dir}", slug=context.slug)

    files = sorted(context.md_dir.glob("*.md"))
    logger.info(
        "📄 Trovati %d file markdown",
        len(files),
        extra={"slug": context.slug, "file_path": str(context.md_dir)},
    )
    return files


def _normalize_term(term: str) -> str:
    """Sanitizza un termine: NFC + rimozione zero-width; non forza lowercase."""
    t = unicodedata.normalize("NFC", str(term).strip())
    t = re.sub(r"[\u200B\u200C\u200D\uFEFF]", "", t)
    return t


def _term_to_pattern(term: str) -> re.Pattern[str]:
    # Allinea la normalizzazione del pattern a quella dei termini/risultati
    t = _normalize_term(term).lower()
    esc = re.escape(t)
    esc = esc.replace(r"\ ", r"\s+")
    # lookaround espliciti per supportare token con punteggiatura (es. c++, ml/ops, data+)
    return re.compile(rf"(?<!\w){esc}(?!\w)")


def extract_semantic_concepts(
    context: _Ctx,
    logger: Optional[logging.Logger] = None,
    *,
    max_scan_bytes: Optional[int] = None,
) -> Dict[str, List[Dict[str, str]]]:
    logger = logger or get_structured_logger("semantic.extract", context=context)

    # Carica i keyword (fase 2) tramite compat-shim (patchabile nei test)
    # NB: niente keyword argument 'logger' per compatibilita con i test legacy
    mapping = load_semantic_mapping(context)
    mapping = _sanitize_and_dedup_mapping(mapping)
    if not mapping:
        logger.warning(
            "⚠️ Mapping semantico vuoto: salto l'estrazione concetti.",
            extra={"slug": context.slug},
        )
        return {}

    markdown_files = _list_markdown_files(context, logger=logger)
    extracted_data: Dict[str, List[Dict[str, str]]] = {}

    for concept, keywords in mapping.items():
        if not keywords:
            extracted_data[concept] = []
            continue

        # normalizza/dedup (case-insensitive) con sanificazione visibile
        seen_norm_lowers: set[str] = set()
        norm_kws: List[str] = []  # termini sanificati per output e pattern
        for kw in keywords:
            k = _normalize_term(kw)
            if not k:
                continue
            key_ci = k.lower()
            if key_ci in seen_norm_lowers:
                continue
            seen_norm_lowers.add(key_ci)
            norm_kws.append(k)

        patterns = [_term_to_pattern(k) for k in norm_kws]

        matches: List[Dict[str, str]] = []
        for file in markdown_files:
            try:
                if max_scan_bytes is not None:
                    try:
                        size = file.stat().st_size
                        if size > max_scan_bytes:
                            logger.info(
                                "⏭️  Skip MD troppo grande",
                                extra={
                                    "slug": context.slug,
                                    "file_path": str(file),
                                    "bytes": size,
                                    "limit": max_scan_bytes,
                                },
                            )
                            continue
                    except Exception:
                        # se stat fallisce, procedi comunque
                        pass

                content = read_text_safe(context.md_dir, file, encoding="utf-8")
                # Normalizza Unicode e rimuove caratteri invisibili che rompono i match
                content = unicodedata.normalize("NFC", content)
                content = re.sub(r"[\u200B\u200C\u200D\uFEFF]", "", content).lower()

                # registra l'indice del primo pattern che fa match
                hit_idx: Optional[int] = None
                for i, pat in enumerate(patterns):
                    if pat.search(content):
                        hit_idx = i
                        break

                if hit_idx is not None:
                    # keyword sanificata (senza char invisibili)
                    matches.append({"file": file.name, "keyword": norm_kws[hit_idx]})
            except Exception as e:
                logger.warning(
                    "⚠️ Impossibile leggere %s: %s",
                    file,
                    e,
                    extra={"slug": context.slug, "file_path": str(file)},
                )
                continue
        extracted_data[concept] = matches

    logger.info("🔍 Estrazione concetti completata", extra={"slug": context.slug})
    return extracted_data


def _enrich_md(context: _Ctx, file: Path, logger: logging.Logger) -> None:
    """Hook di arricchimento per singolo file (no-op idempotente)."""
    try:
        logger.debug("semantic.enrich.noop", extra={"slug": context.slug, "file_path": str(file)})
    except Exception:
        pass


def enrich_markdown_folder(context: _Ctx, logger: Optional[logging.Logger] = None) -> None:
    logger = logger or get_structured_logger("semantic.enrich", context=context)
    markdown_files = _list_markdown_files(context, logger=logger)

    # Consentire disattivazione opzionale via attributo del contesto (se presente)
    try:
        if hasattr(context, "enrich_enabled") and not bool(getattr(context, "enrich_enabled")):
            logger.info(
                "enrich.disabled",
                extra={"slug": context.slug, "file_path": str(context.md_dir)},
            )
            return
    except Exception:
        pass

    logger.info(
        "📂 Avvio arricchimento semantico su %d file",
        len(markdown_files),
        extra={"slug": context.slug, "file_path": str(context.md_dir)},
    )

    for file in markdown_files:
        try:
            logger.debug(
                "✏️ Elaborazione semantica per %s",
                file.name,
                extra={"slug": context.slug, "file_path": str(file)},
            )
            _enrich_md(context, file, logger)
        except Exception as e:
            logger.warning(
                "⚠️ Errore durante arricchimento %s: %s",
                file,
                e,
                extra={"slug": context.slug, "file_path": str(file)},
            )
            continue

    logger.info("✅ Arricchimento semantico completato.", extra={"slug": context.slug})


def load_tags_reviewed(base_dir: Path) -> Dict[str, List[str]]:
    """
    Carica semantic/tags_reviewed.yaml e restituisce {concept: [keywords...]} sanificati.
    """
    base_path = Path(base_dir)
    sem_dir = ensure_within_and_resolve(base_path, base_path / "semantic")
    yaml_path = ensure_within_and_resolve(sem_dir, sem_dir / "tags_reviewed.yaml")
    if not yaml_path.is_file():
        raise FileNotFoundError(f"tags_reviewed.yaml non trovato: {yaml_path}")

    raw = read_text_safe(sem_dir, yaml_path, encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError("Formato tags_reviewed.yaml non valido: atteso dict.")

    raw_tags = data.get("tags") or {}
    if not isinstance(raw_tags, dict):
        raise ValueError("Formato tags_reviewed.yaml non valido: campo 'tags' mancante o non mappa.")

    normalized: Dict[str, List[str]] = {}
    for concept, values in raw_tags.items():
        if isinstance(values, str):
            seq = [values]
        elif isinstance(values, list):
            seq = [str(v) for v in values]
        else:
            seq = [str(values)]
        normalized[str(concept)] = seq

    return _sanitize_and_dedup_mapping(normalized)


def load_semantic_mapping(context: Any, _logger: Optional[logging.Logger] = None) -> Dict[str, List[str]]:
    """
    Shim compatibile con i test legacy: restituisce i keywords di Fase 2.
    """
    base_dir = getattr(context, "base_dir", None)
    if base_dir is None:
        raise PipelineError("Context privo di base_dir per estrazione semantica.", slug=getattr(context, "slug", None))
    try:
        return load_tags_reviewed(Path(base_dir))
    except FileNotFoundError as exc:
        raise PipelineError(
            "tags_reviewed.yaml non trovato (esegui la revisione semantica Fase 2).",
            slug=getattr(context, "slug", None),
            file_path=str(exc),
        ) from exc
    except Exception as exc:
        raise PipelineError(
            f"tags_reviewed.yaml non valido: {exc}",
            slug=getattr(context, "slug", None),
        ) from exc


_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"}


def _sanitize_kw(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch not in _ZERO_WIDTH)
    cleaned = unicodedata.normalize("NFC", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _sanitize_and_dedup_mapping(mapping: Dict[str, List[str]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for concept, values in (mapping or {}).items():
        seen: set[str] = set()
        items: List[str] = []
        for raw_value in values or []:
            candidate = _sanitize_kw(str(raw_value))
            if not candidate:
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(candidate)
        out[str(concept)] = items
    return out


__all__ = ["extract_semantic_concepts", "enrich_markdown_folder", "load_tags_reviewed", "load_semantic_mapping"]
