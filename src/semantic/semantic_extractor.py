# src/semantic/semantic_extractor.py
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from pipeline.exceptions import InputDirectoryMissing, PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import is_safe_subpath
from semantic.semantic_mapping import load_semantic_mapping


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


def _term_to_pattern(term: str) -> re.Pattern[str]:
    # Normalizza Unicode e rimuove caratteri a larghezza zero che possono spezzare i token
    t = unicodedata.normalize("NFC", term.strip().lower())
    t = re.sub(r"[\u200B\u200C\u200D\uFEFF]", "", t)
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

    mapping = load_semantic_mapping(context, logger=logger)
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

        # normalizza/dedup (case-insensitive) mantenendo l'originale
        seen_lowers: set[str] = set()
        norm_kws: List[str] = []
        for kw in keywords:
            k = str(kw).strip()
            if not k:
                continue
            kl = k.lower()
            if kl in seen_lowers:
                continue
            seen_lowers.add(kl)
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

                from pipeline.path_utils import read_text_safe

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


__all__ = ["extract_semantic_concepts", "enrich_markdown_folder"]
