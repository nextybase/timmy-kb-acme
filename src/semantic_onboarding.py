#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# src/semantic_onboarding.py
"""
Semantic Onboarding: RAW → BOOK con arricchimento semantico e preview Docker.

Cosa fa
-------
- Converte i PDF in `output/timmy-kb-<slug>/raw/` in Markdown in `output/timmy-kb-<slug>/book/`.
- Arricchisce i frontmatter dei `.md` usando (se presente) `output/timmy-kb-<slug>/semantic/tags_reviewed.yaml`
  come **SSoT** dei tag (post HiTL).
- Genera `README.md` e `SUMMARY.md` (util di repo se disponibili, altrimenti fallback centralizzati).
- Avvia la preview Docker (HonKit) e gestisce lo stop in modo esplicito.

Nota: **nessun uso di Google Drive** in questo step e **nessun push GitHub** (demandato a `onboarding_full.py`).
"""
from __future__ import annotations

import argparse
import re
import sys
import uuid
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

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
    ensure_valid_slug,  # helper centralizzato
    sorted_paths,
    ensure_within,  # guardia STRONG (SSoT)
)
from pipeline.file_utils import safe_write_text  # scritture atomiche

# Content utils ufficiali (se presenti)
try:
    from pipeline.content_utils import (
        convert_files_to_structured_markdown,  # (context, skip_if_unchanged=None, max_workers=None)
        generate_summary_markdown,  # (context)
        generate_readme_markdown,  # (context)
        validate_markdown_dir,  # (context)
    )
except Exception:
    convert_files_to_structured_markdown = None  # type: ignore
    generate_summary_markdown = None  # type: ignore
    generate_readme_markdown = None  # type: ignore
    validate_markdown_dir = None  # type: ignore

# Adapter: README/SUMMARY fallback uniformi
from adapters.content_fallbacks import ensure_readme_summary

# Adapter: Preview GitBook/HonKit
from adapters.preview import start_preview, stop_preview

# PyYAML per tags_reviewed.yaml e frontmatter
try:
    import yaml  # type: ignore
except Exception:
    yaml = None


# ─────────────── Helpers UX ───────────────
def _prompt(msg: str) -> str:
    """Raccoglie input testuale da CLI (abilitato **solo** negli orchestratori).

    Args:
        msg: Messaggio da visualizzare all’utente.

    Returns:
        Risposta dell’utente ripulita con ``strip()``.
    """
    return input(msg).strip()


# ─────────────── Path helpers ───────────────
def get_paths(slug: str) -> Dict[str, Path]:
    """Calcola i percorsi base per la sandbox cliente.

    Args:
        slug: Identificatore cliente (slug).

    Returns:
        Dizionario con chiavi: `base`, `raw`, `book`, `semantic`.
    """
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}"
    raw_dir = base_dir / "raw"
    book_dir = base_dir / "book"
    semantic_dir = base_dir / "semantic"
    return {"base": base_dir, "raw": raw_dir, "book": book_dir, "semantic": semantic_dir}


# ─────────────── Tags loading (SSoT: tags_reviewed.yaml) ───────────────
def _load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    """
    Costruisce un vocabolario canonico a partire da `semantic/tags_reviewed.yaml`.

    Formato atteso (semplificato):
    {
      version: "1.x",
      reviewed_at: "YYYY-MM-DD",
      keep_only_listed: bool,
      tags: [
        { name: "Canonico", action: "keep"| "drop" | "merge_into:<target>", synonyms: [..], notes: "" },
        ...
      ]
    }

    Output:
      {
        "<canonical>": {"aliases": {<alias1>, <alias2>, ...}}
      }

    Regole:
    - `keep` → canonical = name; aliases = {name} ∪ synonyms
    - `drop` → ignorato (non entra nel vocab)
    - `merge_into:X` → gli alias (name + synonyms) vengono accreditati a canonical=X
      (se X non è ancora presente, viene creato placeholder e poi completato se appare).
    """
    tags_path = base_dir / "semantic" / "tags_reviewed.yaml"

    # Guardia path forte
    try:
        ensure_within(base_dir / "semantic", tags_path)
    except ConfigError:
        logger.warning(
            "tags_reviewed.yaml fuori dalla sandbox semantic/: skip lettura",
            extra={"file_path": str(tags_path)},
        )
        return {}

    if not tags_path.exists():
        logger.info("tags_reviewed.yaml assente: frontmatter con tags vuoti")
        return {}
    if yaml is None:
        logger.warning(
            "PyYAML assente: impossibile leggere tags_reviewed.yaml; proceeding senza tag."
        )
        return {}

    try:
        data = yaml.safe_load(tags_path.read_text(encoding="utf-8")) or {}
        items = data.get("tags", []) or []
        # prima passata: inizializza canonical keep
        vocab: Dict[str, Dict[str, Set[str]]] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            action = str(it.get("action", "")).strip().lower()
            synonyms = [s for s in (it.get("synonyms") or []) if isinstance(s, str)]
            if not name:
                continue
            if action == "keep":
                canon = name
                entry = vocab.setdefault(canon, {"aliases": set()})
                entry["aliases"].add(name)
                entry["aliases"].update({s for s in synonyms if s.strip()})
        # seconda passata: gestisci merge_into
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            action = str(it.get("action", "")).strip().lower()
            synonyms = [s for s in (it.get("synonyms") or []) if isinstance(s, str)]
            if not name or not action.startswith("merge_into:"):
                continue
            target = action.split(":", 1)[1].strip()
            if not target:
                continue
            entry = vocab.setdefault(target, {"aliases": set()})
            entry["aliases"].add(name)
            entry["aliases"].update({s for s in synonyms if s.strip()})
        logger.info("Vocabolario (reviewed) caricato", extra={"canonicals": len(vocab)})
        return vocab
    except (OSError, AttributeError) as e:
        logger.warning(
            "Impossibile leggere tags_reviewed.yaml",
            extra={"file_path": str(tags_path), "error": str(e)},
        )
    except (ValueError, TypeError, yaml.YAMLError) as e:  # type: ignore[attr-defined]
        logger.warning(
            "Impossibile parsare tags_reviewed.yaml",
            extra={"file_path": str(tags_path), "error": str(e)},
        )
    return {}


def _build_inverse_index(vocab: Dict[str, Dict[str, Set[str]]]) -> Dict[str, Set[str]]:
    """Crea un indice inverso {termine_lower: set(canonical)} includendo canonical e alias/sinonimi.

    Args:
        vocab: Mappa dei tag canonici con set di alias.

    Returns:
        Indice inverso dal termine (lowercased) all’insieme di tag canonici che lo contengono.
    """
    inv: Dict[str, Set[str]] = {}
    for canon, meta in (vocab or {}).items():
        # canonical stesso è alias implicito
        for term in {canon, *(meta.get("aliases") or set())}:
            t = str(term).strip().lower()
            if t:
                inv.setdefault(t, set()).add(canon)
    return inv


def _guess_tags_for_name(
    name_like_path: str,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    inv: Optional[Dict[str, Set[str]]] = None,
) -> List[str]:
    """Estrae la lista di **tag canonici** (reviewed) individuati nel nome/percorso del file.

    Args:
        name_like_path: Nome file o percorso “name-like” da analizzare.
        vocab: Vocabolario canonico generato da `_load_reviewed_vocab`.
        inv: (opz.) indice inverso precomputato; se assente verrà generato al volo.

    Returns:
        Lista ordinata di tag canonici rilevati nel nome/percorso.
    """
    if not vocab:
        return []
    if inv is None:
        inv = _build_inverse_index(vocab)

    s = name_like_path.lower()
    s = re.sub(r"[_\\/\-\s]+", " ", s)

    found: Set[str] = set()
    for term, canon_set in inv.items():
        if term and term in s:
            found.update(canon_set)
    return sorted(found)


# ─────────────── Frontmatter helpers ───────────────
def _parse_frontmatter(md_text: str) -> Tuple[Dict, str]:
    """Parsa un frontmatter YAML iniziale restituendo metadati e corpo.

    Regole:
    - Richiede un blocco iniziale delimitato da linee '---' (supporta LF o CRLF).
    - Se parsing fallisce o non presente, restituisce meta vuoto + testo originale.

    Args:
        md_text: Testo Markdown completo da analizzare.

    Returns:
        Tuple `(meta, body)`: dizionario dei metadati e corpo del documento.
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
        body = md_text[m.end() :]
        meta = yaml.safe_load(header) or {}
        if not isinstance(meta, dict):
            return {}, md_text
        return meta, body
    except (ValueError, TypeError, yaml.YAMLError):  # type: ignore[attr-defined]
        return {}, md_text


def _dump_frontmatter(meta: Dict) -> str:
    """Serializza un dizionario frontmatter in YAML “header” (con fallback robusti).

    Args:
        meta: Dizionario dei metadati (es. `title`, `tags`).

    Returns:
        Stringa YAML delimitata da `---` pronta da premettere al corpo Markdown.
    """
    if yaml is None:
        lines = ["---"]
        if "title" in meta:
            title_val = str(meta["title"]).replace('"', '\\"')
            lines.append(f'title: "{title_val}"')
        if "tags" in meta and isinstance(meta["tags"], list):
            lines.append("tags:")
            lines.extend([f"  - {t}" for t in meta["tags"]])
        lines.append("---\n")
        return "\n".join(lines)
    try:
        return (
            "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip() + "\n---\n"
        )
    except (ValueError, TypeError, yaml.YAMLError):  # type: ignore[attr-defined]
        lines = ["---"]
        if "title" in meta:
            title_val = str(meta["title"]).replace('"', '\\"')
            lines.append(f'title: "{title_val}"')  # fallback sicuro se YAML fallisce
        if "tags" in meta and isinstance(meta["tags"], list):
            lines.append("tags:")
            lines.extend([f"  - {t}" for t in meta["tags"]])
        lines.append("---\n")
        return "\n".join(lines)


def _merge_frontmatter(existing: Dict, *, title: Optional[str], tags: List[str]) -> Dict:
    """Unisce metadati esistenti con `title` (se mancante) e un set di `tags` consolidati.

    Args:
        existing: Frontmatter già presente (può essere vuoto).
        title: Titolo proposto (usato solo se `existing` non contiene `title`).
        tags: Lista di tag canonici da integrare.

    Returns:
        Dizionario frontmatter risultante, con `tags` deduplicati e ordinati.
    """
    meta = dict(existing or {})
    if title and not meta.get("title"):
        meta["title"] = title
    if tags:
        meta["tags"] = sorted(set((meta.get("tags") or []) + tags))
    return meta


# ─────────────── RAW → BOOK ───────────────
def _convert_raw_to_book(
    context: ClientContext, logger: logging.Logger, *, slug: str
) -> List[Path]:
    """Converte i PDF presenti in `raw/` in file Markdown sotto `book/`.

    Note:
        Se `convert_files_to_structured_markdown` non è disponibile, effettua un fallback
        che lascia invariata la directory `book/` (solo warning).

    Args:
        context: Contesto cliente.
        logger: Logger strutturato.
        slug: Identificatore cliente (slug).

    Returns:
        Lista di percorsi `.md` in `book/` dopo la conversione (o stato attuale in fallback).

    Raises:
        ConfigError: Se `raw/` non esiste o non contiene PDF quando l’utility di conversione è disponibile.
    """
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
        logger.warning(
            "convert_files_to_structured_markdown non disponibile: skip conversione (fallback)"
        )
        mds = list(sorted_paths(book_dir.glob("*.md"), base=book_dir))
        if not mds:
            logger.warning("Nessun .md in book/: conversione non disponibile e directory vuota")
        return mds

    # Parametri extra opzionali passati come kwargs, ignorati se non supportati (compat formale)
    if convert_files_to_structured_markdown is not None:
        try:
            convert_files_to_structured_markdown(context, skip_if_unchanged=None, max_workers=None)  # type: ignore[call-arg]
        except TypeError:
            # Firme più vecchie non accettano questi kwargs; richiama senza
            convert_files_to_structured_markdown(context)  # type: ignore[misc]
    return sorted_paths(book_dir.glob("*.md"), base=book_dir)


def _enrich_frontmatter(
    context: ClientContext,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    slug: str,
) -> List[Path]:
    """Arricchisce i frontmatter dei `.md` in `book/` con `title` e `tags` canonici (se disponibili).

    Args:
        context: Contesto cliente.
        logger: Logger strutturato.
        vocab: Vocabolario canonico caricato da `_load_reviewed_vocab`.
        slug: Identificatore cliente (slug).

    Returns:
        Lista dei file `.md` modificati durante l’arricchimento.
    """
    paths = get_paths(slug)
    book_dir = paths["book"]
    mds = sorted_paths(book_dir.glob("*.md"), base=book_dir)
    touched: List[Path] = []

    inv = _build_inverse_index(vocab)

    for md in mds:
        name = md.name
        title = re.sub(r"[_\\/\-]+", " ", Path(name).stem).strip() or "Documento"
        tags = _guess_tags_for_name(name, vocab, inv=inv)

        try:
            text = md.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Impossibile leggere MD", extra={"file_path": str(md), "error": str(e)})
            continue

        meta, body = _parse_frontmatter(text)
        new_meta = _merge_frontmatter(meta, title=title, tags=tags)
        if meta == new_meta:
            continue

        fm = _dump_frontmatter(new_meta)
        try:
            ensure_within(book_dir, md)  # path-safety forte
            safe_write_text(md, fm + body, encoding="utf-8", atomic=True)
            touched.append(md)
            logger.info("Frontmatter arricchito", extra={"file_path": str(md), "tags": tags})
        except OSError as e:
            logger.warning("Scrittura MD fallita", extra={"file_path": str(md), "error": str(e)})

    return touched


def _write_summary_and_readme(context: ClientContext, logger: logging.Logger, *, slug: str) -> None:
    """Genera/valida `SUMMARY.md` e `README.md` in `book/` usando util ufficiali o fallback centralizzati.

    Strategia:
      1) Tenta `generate_summary_markdown` e `generate_readme_markdown` se disponibili.
      2) Applica sempre `ensure_readme_summary` come fallback idempotente.
      3) Esegue `validate_markdown_dir` se presente (best-effort).

    Args:
        context: Contesto cliente.
        logger: Logger strutturato.
        slug: Identificatore cliente (slug).
    """
    # 1) Tenta utility ufficiali
    if generate_summary_markdown is not None:
        try:
            generate_summary_markdown(context)
            logger.info("SUMMARY.md scritto (repo util)")
        except Exception as e:
            logger.warning(
                "generate_summary_markdown fallita; procederò con fallback", extra={"error": str(e)}
            )

    if generate_readme_markdown is not None:
        try:
            generate_readme_markdown(context)
            logger.info("README.md scritto (repo util)")
        except Exception as e:
            logger.warning(
                "generate_readme_markdown fallita; potrei usare il fallback",
                extra={"error": str(e)},
            )

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
    preview_port: Optional[int] = None,
    run_id: Optional[str] = None,
) -> None:
    """Esegue l’onboarding semantico: conversione RAW→BOOK, arricchimento frontmatter, README/SUMMARY, preview.

    Precedence porta preview:
      1) Argomento CLI `preview_port` (se passato)
      2) Variabile d’ambiente `PREVIEW_PORT`
      3) Config cliente (`config.yaml` → chiave `preview_port`, se presente in `context.config`)
      4) Default 4000

    Args:
        slug: Identificatore cliente (slug) della sandbox `output/`.
        non_interactive: Se True, esecuzione batch senza prompt interattivi.
        with_preview: Se True, prova ad avviare la preview Docker (HonKit).
        preview_port: Porta TCP per la preview (1..65535); se None, verrà risolta come da precedenza.
        run_id: ID di correlazione per i log strutturati.

    Raises:
        ConfigError: Parametri non validi o precondizioni mancanti (es. RAW vuota con util conversione disponibile).
        PipelineError: Errori di pipeline propagati dai moduli/adapter.
    """
    import os  # import locale per evitare modifiche globali

    early_logger = get_structured_logger("semantic_onboarding", run_id=run_id)
    slug = ensure_valid_slug(
        slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger
    )

    # Context
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=False,
        run_id=run_id,
    )

    # Risoluzione porta preview (CLI > ENV > config > default)
    resolved_port: Optional[int] = preview_port
    if resolved_port is None:
        env_val = os.getenv("PREVIEW_PORT")
        if env_val:
            try:
                resolved_port = int(env_val)
            except ValueError:
                early_logger.warning(f"PREVIEW_PORT non valida: {env_val!r} (ignoro)")
    if resolved_port is None:
        try:
            cfg = getattr(context, "config", {}) or {}
            cfg_val = cfg.get("preview_port")
            if cfg_val is not None:
                resolved_port = int(cfg_val)
        except Exception:
            pass
    if resolved_port is None:
        resolved_port = 4000

    # validazione porta preview
    if not (1 <= int(resolved_port) <= 65535):
        raise ConfigError(f"Porta non valida per preview: {resolved_port}")
    preview_port = int(resolved_port)

    # Log path sotto la base cliente con guardia STRONG
    paths = get_paths(slug)
    base_dir = paths["base"]
    log_file = base_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    ensure_within(base_dir / LOGS_DIR_NAME, log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = get_structured_logger(
        "semantic_onboarding", log_file=log_file, context=context, run_id=run_id
    )
    logger.info(
        "🚀 Avvio semantic_onboarding (RAW → BOOK + arricchimento + preview)",
        extra={"preview_port": preview_port},
    )

    # 1) RAW → BOOK
    _convert_raw_to_book(context, logger, slug=slug)

    # 2) Arricchimento frontmatter con semantica (SSoT: tags_reviewed.yaml)
    vocab = _load_reviewed_vocab(base_dir, logger)
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
                logger.info(
                    "Preview lasciata ATTIVA su richiesta utente",
                    extra={"container_name": container_name},
                )

    book_dir = paths["book"]
    logger.info(
        "✅ semantic_onboarding completato",
        extra={"md_files": len(list(book_dir.glob("*.md"))), "preview_container": container_name},
    )


# ─────────────── CLI ───────────────
def _parse_args() -> argparse.Namespace:
    """Parser CLI per semantic_onboarding.

    Opzioni:
        slug_pos: Argomento posizionale per lo slug cliente.
        --slug: Slug cliente (alternativa al posizionale).
        --non-interactive: Esecuzione senza prompt.
        --no-preview: Disabilita l’avvio della preview Docker.
        --preview-port: Porta per la preview (default: 4000).

    Returns:
        argparse.Namespace con i parametri parsati.
    """
    p = argparse.ArgumentParser(
        description="Semantic Onboarding (RAW → BOOK, arricchimento, preview)"
    )
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument("--no-preview", action="store_true", help="Disabilita generazione preview")
    p.add_argument(
        "--preview-port", type=int, default=4000, help="Porta per la preview (se supportato)"
    )
    return p.parse_args()


if __name__ == "__main__":
    """Entrypoint CLI di `semantic_onboarding`.

    Flusso:
      - Parsing della CLI con `_parse_args()`.
      - Creazione `run_id` per i log strutturati.
      - Validazione dello `slug` (interattiva o batch).
      - Invocazione di `semantic_onboarding_main` con le opzioni selezionate.

    Exit codes:
      - 0 → OK.
      - Da `EXIT_CODES` per eccezioni note.
      - 1 per errori non mappati.
    """
    args = _parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("semantic_onboarding", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error(
            "Errore: in modalità non interattiva è richiesto --slug (o slug posizionale)."
        )
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
        sys.exit(0)
    except (ConfigError, PipelineError) as e:
        logger = get_structured_logger("semantic_onboarding", run_id=run_id)
        logger.error(str(e))
        sys.exit(EXIT_CODES.get(type(e).__name__, 1))
