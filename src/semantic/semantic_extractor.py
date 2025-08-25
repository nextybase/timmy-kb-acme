# src/semantic/semantic_extractor.py
"""
Modulo per l'estrazione e l'arricchimento semantico dei documenti markdown
nella pipeline Timmy-KB.

Refactor v1.0.5 (Blocco B):
- Coerenza guardie: se il mapping è vuoto → warning e short-circuit (no I/O inutile).
- Lettura file: soglia opzionale `max_scan_bytes` per evitare scan costosi; se superata,
  logghiamo una micro-nota e saltiamo il file.
- Nessun cambio di contratto per i call-site esistenti (nuovo parametro solo keyword).

Assunzioni:
- Il mapping è **canonico** {concept: [keywords...]} (normalizzato da semantic_mapping).
- Modulo puro, senza I/O interattivo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError, FileNotFoundError, NotADirectoryError
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath
from semantic.semantic_mapping import load_semantic_mapping


def _list_markdown_files(context: ClientContext, logger=None) -> List[Path]:
    """Ritorna la lista ordinata dei file markdown nella directory md_dir del contesto."""
    logger = logger or get_structured_logger("semantic.files", context=context)
    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PipelineError(f"Path non sicuro: {context.md_dir}", slug=context.slug, file_path=context.md_dir)

    if not context.md_dir.exists():
        raise FileNotFoundError(f"Directory markdown non trovata: {context.md_dir}")
    if not context.md_dir.is_dir():
        raise NotADirectoryError(f"Il path non è una directory: {context.md_dir}")

    files = sorted(context.md_dir.glob("*.md"))
    logger.info(
        f"📄 Trovati {len(files)} file markdown in {context.md_dir}",
        extra={"slug": context.slug, "file_path": str(context.md_dir)},
    )
    return files


def extract_semantic_concepts(
    context: ClientContext,
    logger=None,
    *,
    max_scan_bytes: Optional[int] = None,
) -> Dict[str, List[Dict[str, str]]]:
    """
    Estrae i concetti semantici dai file markdown basandosi sul mapping canonico in config/.

    Args:
        context: contesto cliente.
        logger: logger strutturato (opzionale).
        max_scan_bytes: se impostato, i file .md con dimensione > soglia vengono **saltati**
                        (loggando una micro-nota) per evitare scan troppo costosi.

    Returns:
        dict: {concept: [{"file": <name>, "keyword": <kw>}, ...], ...}
    """
    logger = logger or get_structured_logger("semantic.extract", context=context)

    mapping = load_semantic_mapping(context, logger=logger)  # {concept: [keywords...]}

    # Short-circuit: mapping vuoto → niente scan, meno noise/log I/O
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

        matches: List[Dict[str, str]] = []
        for file in markdown_files:
            try:
                # Soglia dimensione opzionale per evitare scan costosi
                if max_scan_bytes is not None:
                    try:
                        size = file.stat().st_size
                        if size > max_scan_bytes:
                            logger.info(
                                "⏭️  Skip MD troppo grande per la scansione",
                                extra={"slug": context.slug, "file_path": str(file), "bytes": size, "limit": max_scan_bytes},
                            )
                            continue
                    except Exception:
                        # best-effort: se stat fallisce, si procede alla lettura
                        pass

                content = file.read_text(encoding="utf-8")
                content_l = content.lower()
                for kw in keywords:
                    k = str(kw).strip()
                    if not k:
                        continue
                    if k.lower() in content_l:
                        matches.append({"file": file.name, "keyword": k})
            except Exception as e:
                logger.warning(
                    f"⚠️ Impossibile leggere {file}: {e}",
                    extra={"slug": context.slug, "file_path": str(file)},
                )
                continue
        extracted_data[concept] = matches

    logger.info("🔍 Estrazione concetti completata", extra={"slug": context.slug})
    return extracted_data


def enrich_markdown_folder(context: ClientContext, logger=None) -> None:
    """Orchestratore dell'arricchimento semantico (placeholder per step futuri)."""
    logger = logger or get_structured_logger("semantic.enrich", context=context)

    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PipelineError(f"Path non sicuro: {context.md_dir}", slug=context.slug, file_path=context.md_dir)

    if not context.md_dir.exists():
        raise FileNotFoundError(f"Directory markdown non trovata: {context.md_dir}")

    markdown_files = _list_markdown_files(context, logger=logger)
    logger.info(
        f"📂 Avvio arricchimento semantico su {len(markdown_files)} file",
        extra={"slug": context.slug, "file_path": str(context.md_dir)},
    )

    for file in markdown_files:
        try:
            logger.debug(
                f"✏️ Elaborazione semantica per {file.name}",
                extra={"slug": context.slug, "file_path": str(file)},
            )
            # TODO: step di arricchimento effettivo
        except Exception as e:
            logger.warning(
                f"⚠️ Errore durante arricchimento {file}: {e}",
                extra={"slug": context.slug, "file_path": str(file)},
            )
            continue

    logger.info("✅ Arricchimento semantico completato.", extra={"slug": context.slug})
