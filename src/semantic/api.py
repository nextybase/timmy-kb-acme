# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/api.py
from __future__ import annotations

import inspect
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, cast

from kb_db import get_db_path as _get_db_path
from kb_db import init_db as _init_kb_db
from kb_db import insert_chunks as _insert_chunks
from pipeline.constants import OUTPUT_DIR_NAME, REPO_NAME_PREFIX
from pipeline.content_utils import convert_files_to_structured_markdown as _convert_md
from pipeline.content_utils import generate_readme_markdown as _gen_readme
from pipeline.content_utils import generate_summary_markdown as _gen_summary
from pipeline.content_utils import validate_markdown_dir as _validate_md
from pipeline.embedding_utils import normalize_embeddings
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import phase_scope
from pipeline.path_utils import ensure_within, sorted_paths
from semantic.auto_tagger import extract_semantic_candidates as _extract_candidates
from semantic.auto_tagger import render_tags_csv as _render_tags_csv
from semantic.config import load_semantic_config as _load_semantic_config
from semantic.normalizer import normalize_tags as _normalize_tags
from semantic.tags_extractor import copy_local_pdfs_to_raw as _copy_local_pdfs_to_raw
from semantic.tags_io import write_tagging_readme as _write_tagging_readme
from semantic.types import EmbeddingsClient as _EmbeddingsClient
from semantic.vocab_loader import load_reviewed_vocab as _load_reviewed_vocab

if TYPE_CHECKING:
    from pipeline.context import ClientContext as ClientContextType
else:
    from semantic.types import ClientContextProtocol as ClientContextType

__all__ = [
    "get_paths",
    "load_reviewed_vocab",
    "convert_markdown",
    "enrich_frontmatter",
    "write_summary_and_readme",
    "build_tags_csv",
    "build_markdown_book",
    "index_markdown_to_db",
    "copy_local_pdfs_to_raw",
    "list_content_markdown",
]


def get_paths(slug: str) -> Dict[str, Path]:
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}"
    return {
        "base": base_dir,
        "raw": base_dir / "raw",
        "book": base_dir / "book",
        "semantic": base_dir / "semantic",
    }


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    return cast(Dict[str, Dict[str, Set[str]]], _load_reviewed_vocab(base_dir, logger))


class _CtxShim:
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str

    def __init__(self, *, base_dir: Path, raw_dir: Path, md_dir: Path, slug: str) -> None:
        self.base_dir = base_dir
        self.raw_dir = raw_dir
        self.md_dir = md_dir
        self.slug = slug


def _resolve_ctx_paths(context: ClientContextType, slug: str) -> tuple[Path, Path, Path]:
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    raw_dir = cast(Path, getattr(context, "raw_dir", None) or (base_dir / "raw"))
    md_dir = cast(Path, getattr(context, "md_dir", None) or (base_dir / "book"))
    return base_dir, raw_dir, md_dir


def _call_convert_md(func: Any, ctx: _CtxShim, md_dir: Path) -> None:
    """Invoca il converter garantendo un fail-fast coerente se la firma è incompatibile."""
    if not callable(func):
        raise ConversionError("convert_md target is not callable", slug=ctx.slug, file_path=md_dir)
    sig = inspect.signature(func)
    params = sig.parameters
    kwargs: Dict[str, Any] = {}
    if "md_dir" in params:
        kwargs["md_dir"] = md_dir
    try:
        bound = sig.bind_partial(ctx, **kwargs)
        bound.apply_defaults()
        func(*bound.args, **bound.kwargs)
    except TypeError as e:
        # Wrappa i TypeError (firma non compatibile) in ConversionError con contesto
        raise ConversionError(f"convert_md call failed: {e}", slug=ctx.slug, file_path=md_dir) from e


# ---------------------------
# Helper DRY / SRP (PR1)
# ---------------------------
def _collect_safe_pdfs(raw_dir: Path, logger: logging.Logger, slug: str) -> tuple[list[Path], int]:
    """Raccoglie PDF sotto raw_dir applicando path-safety forte e scartando symlink/percorsi insicuri.

    Restituisce (lista_pdf_sicuri, conteggio_scartati).
    Log coerenti con semantic.convert.skip_symlink / semantic.convert.skip_unsafe.
    """
    # Import runtime per consentire ai test di monkeypatchare path_utils.ensure_within_and_resolve
    from pipeline import path_utils as ppath

    safe: list[Path] = []
    discarded = 0
    for candidate in sorted_paths(raw_dir.rglob("*.pdf"), base=raw_dir):
        try:
            if candidate.is_symlink():
                logger.warning("semantic.convert.skip_symlink", extra={"slug": slug, "file_path": str(candidate)})
                discarded += 1
                continue
            # Verifica perimetro e risoluzione path (monkeypatchable nei test)
            ppath.ensure_within_and_resolve(raw_dir, candidate)
            safe.append(candidate)
        except Exception as exc:
            logger.warning(
                "semantic.convert.skip_unsafe",
                extra={"slug": slug, "file_path": str(candidate), "error": str(exc)},
            )
            discarded += 1
            continue
    return safe, discarded


def list_content_markdown(book_dir: Path) -> list[Path]:
    """Elenco dei Markdown 'di contenuto' in book_dir, escludendo README/SUMMARY."""
    return [
        p
        for p in sorted_paths(book_dir.glob("*.md"), base=book_dir)
        if p.name.lower() not in {"readme.md", "summary.md"}
    ]


def convert_markdown(context: ClientContextType, logger: logging.Logger, *, slug: str) -> List[Path]:
    """Converte i PDF in RAW in Markdown strutturato dentro book/.

    Regole:
    - Se RAW **non esiste** → ConfigError.
    - Se RAW **non contiene PDF**:
        - NON invocare il converter (evita segnaposto).
        - Se in book/ ci sono già MD di contenuto → restituiscili.
        - Altrimenti → ConfigError (fail-fast).
    - Se RAW **contiene PDF** → invoca sempre il converter.
    """
    start_ts = time.perf_counter()
    base_dir, raw_dir, book_dir = _resolve_ctx_paths(context, slug)
    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, book_dir)

    if not raw_dir.exists():
        raise ConfigError(f"Cartella RAW locale non trovata: {raw_dir}", slug=slug, file_path=raw_dir)
    # NEW: Guard-rail — RAW deve essere una directory (fail-fast tipizzato)
    if not raw_dir.is_dir():
        raise ConfigError(f"Percorso RAW non è una directory: {raw_dir}", slug=slug, file_path=raw_dir)

    book_dir.mkdir(parents=True, exist_ok=True)
    shim = _CtxShim(base_dir=base_dir, raw_dir=raw_dir, md_dir=book_dir, slug=slug)

    # Lista PDF sicura prima del phase_scope per decisione di flusso (path-safety per-file)
    safe_pdfs, discarded_unsafe = _collect_safe_pdfs(raw_dir, logger, slug)

    # KPI aggregato sui PDF scartati (se > 0)
    if discarded_unsafe > 0:
        logger.info("semantic.convert.discarded_unsafe", extra={"slug": slug, "count": discarded_unsafe})

    with phase_scope(logger, stage="convert_markdown", customer=slug) as m:
        if safe_pdfs:
            _call_convert_md(_convert_md, shim, book_dir)
            content_mds = list_content_markdown(book_dir)
        else:
            # RAW senza PDF: non convertire; usa eventuali MD già presenti
            content_mds = list_content_markdown(book_dir)

        try:
            m.set_artifacts(len(content_mds))
        except Exception:
            m.set_artifacts(None)

    if safe_pdfs:
        # Caso con PDF: se non abbiamo ottenuto contenuti, è anomalia di conversione
        if content_mds:
            ms = int((time.perf_counter() - start_ts) * 1000)
            logger.info(
                "sem.convert_markdown.done",
                extra={"slug": slug, "ms": ms, "artifacts": {"content_files": len(content_mds)}},
            )
            return content_mds
        raise ConversionError(
            "La conversione non ha prodotto Markdown di contenuto (solo README/SUMMARY).",
            slug=slug,
            file_path=book_dir,
        )
    else:
        # Caso senza PDF validi
        if content_mds:
            return content_mds
        if discarded_unsafe > 0:
            # RAW conteneva PDF ma tutti scartati per path-safety/symlink
            raise ConfigError(
                (
                    "Trovati solo PDF non sicuri/fuori perimetro in RAW. "
                    "Rimuovi i symlink o sposta i PDF reali dentro 'raw/' e riprova."
                ),
                slug=slug,
                file_path=raw_dir,
            )
        # RAW vuota (nessun PDF trovato)
        raise ConfigError(f"Nessun PDF trovato in RAW locale: {raw_dir}", slug=slug, file_path=raw_dir)


def enrich_frontmatter(
    context: ClientContextType,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    slug: str,
) -> List[Path]:
    from pipeline.path_utils import read_text_safe

    start_ts = time.perf_counter()
    base_dir, raw_dir, book_dir = _resolve_ctx_paths(context, slug)  # noqa: F841
    ensure_within(base_dir, book_dir)

    mds = sorted_paths(book_dir.glob("*.md"), base=book_dir)
    touched: List[Path] = []
    inv = _build_inverse_index(vocab)

    with phase_scope(logger, stage="enrich_frontmatter", customer=slug) as m:
        for md in mds:
            name = md.name
            title = re.sub(r"[_\/\-\s]+", " ", Path(name).stem).strip().replace("  ", " ") or "Documento"
            tags = _guess_tags_for_name(name, vocab, inv=inv)
            try:
                text = read_text_safe(book_dir, md, encoding="utf-8")
            except OSError as e:
                logger.warning(
                    "semantic.frontmatter.read_failed",
                    extra={"slug": slug, "file_path": str(md), "error": str(e)},
                )
                continue
            meta, body = _parse_frontmatter(text)
            new_meta = _merge_frontmatter(meta, title=title, tags=tags)
            if meta == new_meta:
                continue
            fm = _dump_frontmatter(new_meta)
            try:
                ensure_within(book_dir, md)
                safe_write_text(md, fm + body, encoding="utf-8", atomic=True)
                touched.append(md)
                logger.info(
                    "semantic.frontmatter.updated",
                    extra={"slug": slug, "file_path": str(md), "tags": tags},
                )
            except OSError as e:
                logger.warning(
                    "semantic.frontmatter.write_failed",
                    extra={"slug": slug, "file_path": str(md), "error": str(e)},
                )
        try:
            m.set_artifacts(len(touched))
        except Exception:
            m.set_artifacts(None)
    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "sem.enrich_frontmatter.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"updated": len(touched)}},
    )
    return touched


def write_summary_and_readme(context: ClientContextType, logger: logging.Logger, *, slug: str) -> None:
    start_ts = time.perf_counter()
    base_dir, raw_dir, book_dir = _resolve_ctx_paths(context, slug)
    shim = _CtxShim(base_dir=base_dir, raw_dir=raw_dir, md_dir=book_dir, slug=slug)

    errors: list[str] = []
    with phase_scope(logger, stage="write_summary_and_readme", customer=slug) as m:
        # SUMMARY
        try:
            _gen_summary(shim)
            logger.info(
                "semantic.summary.written",
                extra={"slug": slug, "file_path": str(book_dir / "SUMMARY.md")},
            )
        except Exception as e:  # pragma: no cover
            summary_path = book_dir / "SUMMARY.md"
            # Compat test legacy: messaggio letterale
            logger.error(
                "Generazione SUMMARY.md fallita",
                extra={"slug": slug, "file_path": str(summary_path)},
            )
            # Evento strutturato con stacktrace
            logger.exception(
                "semantic.summary.failed",
                extra={"slug": slug, "file_path": str(summary_path), "error": str(e)},
            )
            errors.append(f"summary: {e}")

        # README
        try:
            _gen_readme(shim)
            logger.info(
                "semantic.readme.written",
                extra={"slug": slug, "file_path": str(book_dir / "README.md")},
            )
        except Exception as e:  # pragma: no cover
            readme_path = book_dir / "README.md"
            # Compat test legacy (se in futuro ci fosse un test analogo)
            logger.error(
                "Generazione README.md fallita",
                extra={"slug": slug, "file_path": str(readme_path)},
            )
            logger.exception(
                "semantic.readme.failed",
                extra={"slug": slug, "file_path": str(readme_path), "error": str(e)},
            )
            errors.append(f"readme: {e}")

        if errors:
            raise ConversionError("; ".join(errors), slug=slug, file_path=book_dir)

        _validate_md(shim)
        logger.info("semantic.book.validated", extra={"slug": slug, "book_dir": str(book_dir)})
        m.set_artifacts(2)
    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "sem.summary_readme.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"summary": True, "readme": True}},
    )


def build_tags_csv(context: ClientContextType, logger: logging.Logger, *, slug: str) -> Path:
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    raw_dir = cast(Path, getattr(context, "raw_dir", None) or paths["raw"])
    semantic_dir = base_dir / "semantic"
    csv_path = semantic_dir / "tags_raw.csv"

    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, semantic_dir)
    ensure_within(semantic_dir, csv_path)

    semantic_dir.mkdir(parents=True, exist_ok=True)
    with phase_scope(logger, stage="build_tags_csv", customer=slug) as m:
        cfg = _load_semantic_config(base_dir)
        candidates = _extract_candidates(raw_dir, cfg)
        candidates = _normalize_tags(candidates, cfg.mapping)
        _render_tags_csv(candidates, csv_path, base_dir=base_dir)
        count = len(candidates)
        logger.info(
            "semantic.tags_csv.built",
            extra={"slug": slug, "file_path": str(csv_path), "count": count},
        )
        _write_tagging_readme(semantic_dir, logger)
        try:
            m.set_artifacts(count)
        except Exception:
            m.set_artifacts(None)
    return csv_path


def copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger: logging.Logger) -> int:
    return int(_copy_local_pdfs_to_raw(src_dir, raw_dir, logger))


def build_markdown_book(context: ClientContextType, logger: logging.Logger, *, slug: str) -> list[Path]:
    """Fase unica che copre conversione, summary/readme e arricchimento frontmatter."""
    start_ts = time.perf_counter()
    with phase_scope(logger, stage="build_markdown_book", customer=slug) as m:
        mds = convert_markdown(context, logger, slug=slug)
        write_summary_and_readme(context, logger, slug=slug)

        ctx_base = cast(Path, getattr(context, "base_dir", None))
        base_dir = ctx_base if ctx_base is not None else get_paths(slug)["base"]

        vocab = load_reviewed_vocab(base_dir, logger)
        # Enrichment sempre eseguito: con vocab vuoto aggiorna comunque i titoli/frontmatter.
        enrich_frontmatter(context, logger, vocab, slug=slug)

        try:
            # Artifacts = numero di MD di contenuto (coerente con convert_markdown)
            m.set_artifacts(len(mds))
        except Exception:
            m.set_artifacts(None)
    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "sem.book.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"content_files": len(mds)}},
    )
    return mds


def index_markdown_to_db(
    context: ClientContextType,
    logger: logging.Logger,
    *,
    slug: str,
    scope: str = "book",
    embeddings_client: _EmbeddingsClient,
    db_path: Path | None = None,
) -> int:
    """Indicizza i Markdown presenti in `book/` nel DB con embeddings."""
    start_ts = time.perf_counter()
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    book_dir = cast(Path, getattr(context, "md_dir", None) or paths["book"])
    ensure_within(base_dir, book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)

    files = list_content_markdown(book_dir)
    if not files:
        # NEW: telemetria completa anche su branch "vuoto"
        with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as m:
            logger.info("semantic.index.no_files", extra={"slug": slug, "book_dir": str(book_dir)})
            try:
                m.set_artifacts(0)
            except Exception:
                m.set_artifacts(None)
        ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(
            "sem.index.done",
            extra={"slug": slug, "ms": ms, "artifacts": {"inserted": 0, "files": 0}},
        )
        return 0

    from pipeline.path_utils import read_text_safe

    contents: list[str] = []
    rel_paths: list[str] = []
    skipped_io = 0
    skipped_no_text = 0

    for f in files:
        try:
            text = read_text_safe(book_dir, f, encoding="utf-8")
        except Exception as e:
            logger.warning(
                "semantic.index.read_failed",
                extra={"slug": slug, "file_path": str(f), "error": str(e)},
            )
            skipped_io += 1
            continue
        if not text or not text.strip():
            skipped_no_text += 1
            continue
        contents.append(text)
        rel_paths.append(f.name)

    if not contents:
        # NEW: phase_scope anche su "no contents"
        with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as m:
            logger.info("semantic.index.no_valid_contents", extra={"slug": slug, "book_dir": str(book_dir)})
            if skipped_io > 0 or skipped_no_text > 0:
                logger.info(
                    "semantic.index.skips",
                    extra={
                        "slug": slug,
                        "skipped_io": skipped_io,
                        "skipped_no_text": skipped_no_text,
                        "vectors_empty": 0,
                    },
                )
            try:
                m.set_artifacts(0)
            except Exception:
                m.set_artifacts(None)
        ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(
            "sem.index.done",
            extra={"slug": slug, "ms": ms, "artifacts": {"inserted": 0, "files": len(files)}},
        )
        return 0

    from datetime import datetime as _dt

    with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as m:
        try:
            _init_kb_db(db_path)
        except Exception as e:
            try:
                effective = _get_db_path() if db_path is None else Path(db_path).resolve()
            except Exception:
                effective = db_path or Path("data/kb.sqlite")
            raise ConfigError(
                f"Inizializzazione DB fallita: {e}",
                slug=slug,
                file_path=effective,
            ) from e

        vecs_raw = embeddings_client.embed_texts(contents)
        vecs = normalize_embeddings(vecs_raw)

        if len(vecs) == 0:
            logger.warning("semantic.index.no_embeddings", extra={"slug": slug, "count": 0})
            try:
                m.set_artifacts(0)
            except Exception:
                m.set_artifacts(None)
            # Aggregato skip (nessun embedding generato)
            logger.info(
                "semantic.index.skips",
                extra={
                    "slug": slug,
                    "skipped_io": skipped_io,
                    "skipped_no_text": skipped_no_text,
                    "vectors_empty": 0,
                },
            )
            ms = int((time.perf_counter() - start_ts) * 1000)
            logger.info(
                "sem.index.done",
                extra={"slug": slug, "ms": ms, "artifacts": {"inserted": 0, "files": len(files)}},
            )
            return 0

        # NEW: indicizzazione parziale su mismatch (senza abort)
        if len(vecs) != len(contents):
            logger.warning(
                "semantic.index.mismatched_embeddings",
                extra={"slug": slug, "embeddings": len(vecs), "contents": len(contents)},
            )
            min_len = min(len(vecs), len(contents))
            dropped_mismatch = (len(contents) - min_len) + (len(vecs) - min_len)
            if dropped_mismatch > 0:
                logger.info("semantic.index.embedding_pruned", extra={"slug": slug, "dropped": dropped_mismatch})
                logger.info(
                    "semantic.index.skips",
                    extra={
                        "slug": slug,
                        "skipped_io": skipped_io,
                        "skipped_no_text": skipped_no_text,
                        "vectors_empty": dropped_mismatch,
                    },
                )
            contents = contents[:min_len]
            rel_paths = rel_paths[:min_len]
            vecs = vecs[:min_len]

        filtered_contents: list[str] = []
        filtered_paths: list[str] = []
        filtered_vecs: list[list[float]] = []
        for text, rel_name, emb in zip(contents, rel_paths, vecs, strict=False):
            if len(emb) == 0:
                continue
            filtered_contents.append(text)
            filtered_paths.append(rel_name)
            filtered_vecs.append(list(emb))

        dropped = len(contents) - len(filtered_contents)
        if dropped > 0 and len(filtered_contents) == 0:
            # 👇 Compat test legacy + evento strutturato
            logger.warning("Primo vettore embedding vuoto", extra={"slug": slug})
            logger.warning("semantic.index.all_embeddings_empty", extra={"slug": slug, "count": len(vecs)})
            try:
                m.set_artifacts(0)
            except Exception:
                m.set_artifacts(None)
            # Aggregato skip
            logger.info(
                "semantic.index.skips",
                extra={
                    "slug": slug,
                    "skipped_io": skipped_io,
                    "skipped_no_text": skipped_no_text,
                    "vectors_empty": dropped,
                },
            )
            ms = int((time.perf_counter() - start_ts) * 1000)
            logger.info(
                "sem.index.done",
                extra={"slug": slug, "ms": ms, "artifacts": {"inserted": 0, "files": len(files)}},
            )
            return 0
        if dropped > 0:
            # Log strutturato + messaggio umano per i test (cerca 'scartati'/'dropped')
            logger.info("semantic.index.embedding_pruned", extra={"slug": slug, "dropped": dropped})
            logger.info("Embeddings scartati (dropped): %s", dropped)

        # KPI aggregato sugli skip (solo se c'è almeno uno > 0)
        if skipped_io > 0 or skipped_no_text > 0 or dropped > 0:
            logger.info(
                "semantic.index.skips",
                extra={
                    "slug": slug,
                    "skipped_io": skipped_io,
                    "skipped_no_text": skipped_no_text,
                    "vectors_empty": dropped,
                },
            )

        contents, rel_paths, vecs = filtered_contents, filtered_paths, filtered_vecs

        version = _dt.utcnow().strftime("%Y%m%d")
        inserted_total = 0
        for text, rel_name, emb in zip(contents, rel_paths, vecs, strict=False):
            meta = {"file": rel_name}
            inserted_total += _insert_chunks(
                project_slug=slug,
                scope=scope,
                path=rel_name,
                version=version,
                meta_dict=meta,
                chunks=[text],
                embeddings=[list(emb)],
                db_path=db_path,
                ensure_schema=False,
            )

        logger.info(
            "semantic.index.completed",
            extra={"slug": slug, "inserted": inserted_total, "files": len(rel_paths)},
        )
        ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(
            "sem.index.done",
            extra={"slug": slug, "ms": ms, "artifacts": {"inserted": inserted_total, "files": len(rel_paths)}},
        )
        try:
            m.set_artifacts(inserted_total)
        except Exception:
            m.set_artifacts(None)
        return inserted_total


def _build_inverse_index(vocab: Dict[str, Dict[str, Set[str]]]) -> Dict[str, Set[str]]:
    inv: Dict[str, Set[str]] = {}
    for canon, meta in (vocab or {}).items():
        for term in {canon, *(meta.get("aliases") or set())}:
            t = str(term).strip().lower()
            if t:
                inv.setdefault(t, set()).add(canon)
    return inv


def _parse_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    if not md_text.startswith("---"):
        return {}, md_text
    try:
        import yaml
    except Exception:
        return {}, md_text
    try:
        import re as _re

        m = _re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md_text, flags=_re.DOTALL)
        if not m:
            return {}, md_text
        header = m.group(1)
        body = md_text[m.end() :]
        meta = yaml.safe_load(header) or {}
        if not isinstance(meta, dict):
            return {}, md_text
        return cast(Dict[str, Any], meta), body
    except Exception:
        return {}, md_text


def _dump_frontmatter(meta: Dict[str, Any]) -> str:
    try:
        import yaml

        return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip() + "\n---\n"
    except Exception:
        lines = ["---"]
        if "title" in meta:
            title_val = str(meta["title"]).replace('"', '\\"')
            lines.append(f'title: "{title_val}"')
        if "tags" in meta and isinstance(meta["tags"], list):
            lines.append("tags:")
            lines.extend([f"  - {t}" for t in meta["tags"]])
        lines.append("---\n")
        return "\n".join(lines)


def _as_list_str(x: Any) -> list[str]:
    if x is None:
        return []
    if isinstance(x, str):
        s = x.strip()
        return [s] if s else []
    if isinstance(x, (list, tuple, set)):
        out: list[str] = []
        for it in x:
            if it is None:
                continue
            s = str(it).strip()
            if s:
                out.append(s)
        return out
    s = str(x).strip()
    return [s] if s else []


def _merge_frontmatter(existing: Dict[str, Any], *, title: Optional[str], tags: List[str]) -> Dict[str, Any]:
    meta: Dict[str, Any] = dict(existing or {})
    if title and not meta.get("title"):
        meta["title"] = title
    if tags:
        left = _as_list_str(meta.get("tags"))
        merged = sorted(set(left + list(tags)))
        meta["tags"] = merged
    return meta


@lru_cache(maxsize=1024)
def _term_to_pattern(term: str) -> re.Pattern[str]:
    r"""Pattern robusto a confini parola *semantici* (spazi = \s+)."""
    esc = re.escape(term.strip().lower())
    esc = esc.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){esc}(?!\w)")


def _guess_tags_for_name(
    name_like_path: str,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    inv: Optional[Dict[str, Set[str]]] = None,
) -> List[str]:
    if not vocab:
        return []
    if inv is None:
        inv = _build_inverse_index(vocab)
    s = name_like_path.lower()
    s = re.sub(r"[_\/\-\s]+", " ", s)

    found: Set[str] = set()
    for term, canon_set in inv.items():
        if not term:
            continue
        pat = _term_to_pattern(term)
        if pat.search(s):
            found.update(canon_set)
    return sorted(found)
