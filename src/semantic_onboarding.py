#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semantic Onboarding: RAW → BOOK con arricchimento semantico e preview Docker.
- NON usa Google Drive (i PDF sono già in output/timmy-kb-<slug>/raw/).
- Converte i PDF in Markdown in output/timmy-kb-<slug>/book/ tramite le content utils.
- Arricchisce i frontmatter dei .md usando (se presente) output/timmy-kb-<slug>/semantic/tags.yaml.
- Genera README.md e SUMMARY.md tramite adapters/content_fallbacks (fallback standard centralizzato).
- Avvia la preview Docker (HonKit) e chiede esplicitamente se fermarla prima di uscire.

Nota: nessun push verso GitHub qui. Il push è demandato a `onboarding_full.py`.
"""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --- Infra coerente con orchestratori esistenti ---
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import (
    PipelineError,
    ConfigError,
    EXIT_CODES,
)
from pipeline.context import ClientContext
from pipeline.constants import (
    OUTPUT_DIR_NAME,
    LOGS_DIR_NAME,
    LOG_FILE_NAME,
    REPO_NAME_PREFIX,
)
from pipeline.path_utils import (
    ensure_valid_slug,   # helper centralizzato
    sorted_paths,
    ensure_within,       # guardia STRONG (SSoT)
)
from pipeline.file_utils import safe_write_text  # scritture atomiche
from pipeline.env_utils import compute_redact_flag  # fonte unica flag redaction

# Content utils ufficiali (se presenti)
try:
    from pipeline.content_utils import (
        convert_files_to_structured_markdown,   # (context, skip_if_unchanged=None, max_workers=None)
        generate_summary_markdown,              # (context)
        generate_readme_markdown,               # (context)
        validate_markdown_dir,                  # (context)
    )
except Exception:
    convert_files_to_structured_markdown = None  # type: ignore
    generate_summary_markdown = None             # type: ignore
    generate_readme_markdown = None              # type: ignore
    validate_markdown_dir = None                 # type: ignore

# Adapter: README/SUMMARY fallback uniformi
from adapters.content_fallbacks import ensure_readme_summary
# Adapter: Preview GitBook/HonKit
from adapters.preview import start_preview, stop_preview

# PyYAML per tags.yaml e frontmatter
try:
    import yaml  # type: ignore
except Exception:
    yaml = None


# ─────────────── Helpers UX ───────────────
def _prompt(msg: str) -> str:
    return input(msg).strip()


# ─────────────── Path helpers ───────────────
def get_paths(slug: str) -> Dict[str, Path]:
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}"
    raw_dir = base_dir / "raw"
    book_dir = base_dir / "book"
    semantic_dir = base_dir / "semantic"
    return {"base": base_dir, "raw": raw_dir, "book": book_dir, "semantic": semantic_dir}


# ─────────────── Tags loading ───────────────
def _load_tags_vocab(base_dir: Path, logger) -> Dict[str, Dict]:
    vocab: Dict[str, Dict] = {}
    tags_path = base_dir / "semantic" / "tags.yaml"

    # Guardia path forte prima della lettura
    try:
        ensure_within(base_dir / "semantic", tags_path)
    except ConfigError:
        logger.warning("tags.yaml fuori dalla sandbox semantic/: skip lettura", extra={"file_path": str(tags_path)})
        return vocab

    if not tags_path.exists():
        logger.info("tags.yaml assente: frontmatter con tags vuoti")
        return vocab
    if yaml is None:
        logger.warning("PyYAML assente: impossibile leggere tags.yaml; proceeding senza tag.")
        return vocab

    try:
        data = yaml.safe_load(tags_path.read_text(encoding="utf-8")) or {}
        for item in data.get("tags", []):
            canon = str(item.get("canonical", "")).strip()
            if not canon:
                continue
            vocab[canon] = {
                "synonyms": [s for s in (item.get("synonyms") or []) if isinstance(s, str)],
                "areas_hint": [a for a in (item.get("areas_hint") or []) if isinstance(a, str)],
            }
        logger.info("Vocabolario tag caricato", extra={"count": len(vocab)})
    except Exception as e:
        logger.warning("Impossibile caricare tags.yaml", extra={"error": str(e)})
    return vocab


def _guess_tags_for_name(name_like_path: str, vocab: Dict[str, Dict]) -> Tuple[List[str], List[str]]:
    if not vocab:
        return [], []
    s = name_like_path.lower()
    s = re.sub(r"[_\\/\-\s]+", " ", s)
    found = set()
    areas = set()
    for canon, meta in vocab.items():
        if canon and canon.lower() in s:
            found.add(canon)
        else:
            for syn in meta.get("synonyms", []):
                syn_l = str(syn).lower().strip()
                if syn_l and syn_l in s:
                    found.add(canon)
                    break
    for t in found:
        areas.update(vocab.get(t, {}).get("areas_hint", []))
    return sorted(found), sorted(areas) if areas else []


# ─────────────── Frontmatter helpers ───────────────
def _parse_frontmatter(md_text: str) -> Tuple[Dict, str]:
    """
    Parser frontmatter robusto.
    - Richiede un blocco iniziale delimitato da linee '---' (supporta LF o CRLF).
    - Se parsing fallisce o non presente, restituisce meta vuoto + testo originale.
    """
    if not md_text.startswith("---"):
        return {}, md_text
    if yaml is None:
        return {}, md_text
    try:
        # Cattura tutto tra le prime due linee '---' all'inizio file (LF o CRLF)
        m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md_text, flags=re.DOTALL)
        if not m:
            return {}, md_text
        header = m.group(1)
        body = md_text[m.end():]
        meta = yaml.safe_load(header) or {}
        if not isinstance(meta, dict):
            return {}, md_text
        return meta, body
    except Exception:
        return {}, md_text


def _dump_frontmatter(meta: Dict) -> str:
    if yaml is None:
        lines = ["---"]
        if "title" in meta:
            lines.append(f'title: "{meta["title"]}"')
        if "tags" in meta and isinstance(meta["tags"], list):
            lines.append("tags:")
            lines.extend([f"  - {t}" for t in meta["tags"]])
        if "areas" in meta and isinstance(meta["areas"], list):
            lines.append("areas:")
            lines.extend([f"  - {a}" for a in meta["areas"]])
        lines.append("---\n")
        return "\n".join(lines)
    try:
        return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip() + "\n---\n"
    except Exception:
        lines = ["---"]
        if "title" in meta:
            lines.append(f'title: "{meta["title"]}"')
        if "tags" in meta and isinstance(meta["tags"], list):
            lines.append("tags:")
            lines.extend([f"  - {t}" for t in meta["tags"]])
        if "areas" in meta and isinstance(meta["areas"], list):
            lines.append("areas:")
            lines.extend([f"  - {a}" for a in meta["areas"]])
        lines.append("---\n")
        return "\n".join(lines)


def _merge_frontmatter(existing: Dict, *, title: Optional[str], tags: List[str], areas: List[str]) -> Dict:
    meta = dict(existing or {})
    if title and not meta.get("title"):
        meta["title"] = title
    if tags:
        meta["tags"] = sorted(set((meta.get("tags") or []) + tags))
    if areas:
        meta["areas"] = sorted(set((meta.get("areas") or []) + areas))
    return meta


# ─────────────── RAW → BOOK ───────────────
def _convert_raw_to_book(context: ClientContext, logger, *, slug: str) -> List[Path]:
    paths = get_paths(slug)
    raw_dir = paths["raw"]
    book_dir = paths["book"]

    # Verifica RAW locale e presenza PDF (niente Drive in questo step)
    if not raw_dir.exists():
        raise ConfigError(f"Cartella RAW locale non trovata: {raw_dir}")
    local_pdfs = [p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]
    if not local_pdfs and convert_files_to_structured_markdown is not None:
        raise ConfigError(f"Nessun PDF trovato in RAW locale: {raw_dir}")

    book_dir.mkdir(parents=True, exist_ok=True)

    if convert_files_to_structured_markdown is None:
        logger.warning("convert_files_to_structured_markdown non disponibile: skip conversione (fallback)")
        mds = list(sorted_paths(book_dir.glob("*.md"), base=book_dir))
        if not mds:
            logger.warning("Nessun .md in book/: conversione non disponibile e directory vuota")
        return mds

    convert_files_to_structured_markdown(context, skip_if_unchanged=None, max_workers=None)
    return sorted_paths(book_dir.glob("*.md"), base=book_dir)


def _enrich_frontmatter(context: ClientContext, logger, vocab: Dict[str, Dict], *, slug: str) -> List[Path]:
    paths = get_paths(slug)
    book_dir = paths["book"]
    mds = sorted_paths(book_dir.glob("*.md"), base=book_dir)
    touched: List[Path] = []

    for md in mds:
        name = md.name
        title = re.sub(r"[_\\/\-]+", " ", Path(name).stem).strip() or "Documento"
        tags, areas = _guess_tags_for_name(name, vocab)

        try:
            text = md.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Impossibile leggere MD", extra={"file_path": str(md), "error": str(e)})
            continue

        meta, body = _parse_frontmatter(text)
        new_meta = _merge_frontmatter(meta, title=title, tags=tags, areas=areas)
        if meta == new_meta:
            continue

        fm = _dump_frontmatter(new_meta)
        try:
            ensure_within(book_dir, md)  # path-safety forte
            safe_write_text(md, fm + body, encoding="utf-8", atomic=True)
            touched.append(md)
            logger.info("Frontmatter arricchito", extra={"file_path": str(md), "tags": tags, "areas": areas})
        except Exception as e:
            logger.warning("Scrittura MD fallita", extra={"file_path": str(md), "error": str(e)})

    return touched


def _write_summary_and_readme(context: ClientContext, logger, *, slug: str) -> None:
    paths = get_paths(slug)
    book_dir = paths["book"]

    # 1) Tenta utility ufficiali
    if generate_summary_markdown is not None:
        try:
            generate_summary_markdown(context)
            logger.info("SUMMARY.md scritto (repo util)")
        except Exception as e:
            logger.warning("generate_summary_markdown fallita; procederò con fallback", extra={"error": str(e)})

    if generate_readme_markdown is not None:
        try:
            generate_readme_markdown(context)
            logger.info("README.md scritto (repo util)")
        except Exception as e:
            logger.warning("generate_readme_markdown fallita; potrei usare il fallback", extra={"error": str(e)})

    # 2) Fallback centralizzati via adapter (idempotenti)
    ensure_readme_summary(context, logger)

    # 3) Validazione opzionale
    if validate_markdown_dir is not None:
        try:
            validate_markdown_dir(context)
            logger.info("Validazione directory MD OK")
        except Exception as e:
            logger.warning("Validazione directory MD fallita", extra={"error": str(e)})


# ─────────────── MAIN orchestrator (solo semantica + preview) ───────────────
def semantic_onboarding_main(
    slug: str,
    *,
    non_interactive: bool = False,
    with_preview: bool = True,
    preview_port: int = 4000,
    run_id: Optional[str] = None,
) -> None:
    early_logger = get_structured_logger("semantic_onboarding", run_id=run_id)
    slug = ensure_valid_slug(slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger)

    # validazione porta preview
    if not (1 <= int(preview_port) <= 65535):
        raise ConfigError(f"Porta non valida per preview: {preview_port}")

    # Context
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=False,
        run_id=run_id,
    )
    # Sorgente unica del flag di redazione
    if not hasattr(context, "redact_logs"):
        context.redact_logs = compute_redact_flag(getattr(context, "env", {}), getattr(context, "log_level", "INFO"))

    # Log path sotto la base cliente con guardia STRONG
    paths = get_paths(slug)
    base_dir = paths["base"]
    log_file = base_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    ensure_within(base_dir / LOGS_DIR_NAME, log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = get_structured_logger("semantic_onboarding", log_file=log_file, context=context, run_id=run_id)
    logger.info("🚀 Avvio semantic_onboarding (RAW → BOOK + arricchimento + preview)")

    # 1) RAW → BOOK
    _convert_raw_to_book(context, logger, slug=slug)

    # 2) Arricchimento frontmatter con semantica (se abbiamo il vocabolario)
    vocab = _load_tags_vocab(base_dir, logger)
    if vocab:
        _enrich_frontmatter(context, logger, vocab, slug=slug)

    # 3) SUMMARY.md e README.md (util + fallback centralizzati)
    _write_summary_and_readme(context, logger, slug=slug)

    # 4) Preview (con conferma se interattivo) e chiusura esplicita
    container_name: Optional[str] = None
    if with_preview:
        if not non_interactive:
            ans = (_prompt("Avvio preview Docker di HonKit? (Y/n): ") or "y").lower()
            if ans.startswith("n"):
                with_preview = False
        if with_preview:
            container_name = start_preview(context, logger, port=preview_port)

    if container_name:
        # Domanda esplicita di chiusura prima di uscire
        if non_interactive:
            # In non-interactive non possiamo chiedere: fermiamo per default per lasciare l'ambiente pulito.
            stop_preview(logger, container_name=container_name)
        else:
            stop_now = (_prompt("Chiudo ORA la preview Docker e termino? (Y/n): ") or "y").lower()
            if stop_now.startswith("y"):
                stop_preview(logger, container_name=container_name)
            else:
                logger.info("Preview lasciata ATTIVA su richiesta utente", extra={"container_name": container_name})

    book_dir = paths["book"]
    logger.info("✅ semantic_onboarding completato", extra={"md_files": len(list(book_dir.glob('*.md'))), "preview_container": container_name})


# ─────────────── CLI ───────────────
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Semantic Onboarding (RAW → BOOK, arricchimento, preview)")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument("--no-preview", action="store_true", help="Disabilita generazione preview")
    p.add_argument("--preview-port", type=int, default=4000, help="Porta per la preview (se supportato)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("semantic_onboarding", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error("Errore: in modalità non interattiva è richiesto --slug (o slug posizionale).")
        sys.exit(EXIT_CODES.get("ConfigError", 2))

    try:
        slug = ensure_valid_slug(
            unresolved_slug,
            interactive=not args.non_interactive,
            prompt=_prompt,
            logger=early_logger,
        )
    except ConfigError:
        sys.exit(EXIT_CODES.get("ConfigError", 2))

    try:
        semantic_onboarding_main(
            slug=slug,
            non_interactive=args.non_interactive,
            with_preview=not args.no_preview,
            preview_port=int(args.preview_port),
            run_id=run_id,
        )
    except (ConfigError, PipelineError) as e:
        logger = get_structured_logger("semantic_onboarding", run_id=run_id)
        logger.error(str(e))
        sys.exit(EXIT_CODES.get(type(e).__name__, 1))
