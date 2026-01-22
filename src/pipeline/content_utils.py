# SPDX-License-Identifier: GPL-3.0-only
# src/pipeline/content_utils.py
from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Protocol, TypeAlias, cast
from urllib.parse import quote

from pipeline.exceptions import PathTraversalError, PipelineError
from pipeline.file_utils import safe_write_text  # scritture atomiche
from pipeline.frontmatter_utils import dump_frontmatter as _shared_dump_frontmatter
from pipeline.frontmatter_utils import read_frontmatter
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import iter_safe_paths  # SSoT path-safety forte
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, read_text_safe
from pipeline.tracing import start_decision_span
from pipeline.types import ChunkRecord
from pipeline.workspace_layout import WorkspaceLayout
from semantic.auto_tagger import extract_semantic_candidates
from semantic.config import SemanticConfig, load_semantic_config
from semantic.context_paths import resolve_context_paths
from semantic.types import ClientContextProtocol as _ClientCtx  # SSoT dei contratti

__all__ = [
    "validate_markdown_dir",
    "generate_readme_markdown",
    "generate_summary_markdown",
    "convert_files_to_structured_markdown",
    "log_frontmatter_cache_stats",
    "build_chunk_records_from_markdown_files",
]


class _ReadmeCtx(Protocol):
    repo_root_dir: Path
    slug: str | None


# Alias per annotazioni lunghe (evita E501)
CategoryGroups: TypeAlias = list[tuple[Path, list[Path]]]


class FrontmatterCache:
    """Wrapper LRU leggero per il frontmatter, estendibile con stats/disable."""

    def __init__(self, max_size: int = 256, *, enabled: bool = True) -> None:
        self.max_size = max_size
        self.enabled = enabled
        self._store: OrderedDict[tuple[Path, int, int], tuple[dict[str, Any], str]] = OrderedDict()

    def clear(self, path: Path | None = None) -> None:
        if not self.enabled:
            return
        if path is None:
            self._store.clear()
            return
        for key in list(self._store.keys()):
            if key[0] == path:
                self._store.pop(key, None)

    def get(self, key: tuple[Path, int, int]) -> tuple[dict[str, Any], str] | None:
        if not self.enabled:
            return None
        value = self._store.pop(key, None)
        if value is None:
            return None
        # riposiziona in coda per LRU
        self._store[key] = value
        return value

    def set(self, key: tuple[Path, int, int], value: tuple[dict[str, Any], str]) -> None:
        if not self.enabled:
            return
        self._store.pop(key, None)
        self._store[key] = value
        self._evict()

    def stats(self) -> dict[str, Any]:
        return {"entries": len(self._store), "max": self.max_size, "enabled": self.enabled}

    def _evict(self) -> None:
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)


_FRONTMATTER_CACHE = FrontmatterCache(max_size=256)
_PDF_EXCERPT_MAX_CHARS = 2048


def log_frontmatter_cache_stats(
    logger: logging.Logger,
    event: str = "pipeline.frontmatter_cache.stats",
    *,
    slug: str | None = None,
) -> None:
    """Emette un log debug con le stats correnti della cache frontmatter."""
    try:
        stats = _FRONTMATTER_CACHE.stats()
        extra: dict[str, Any] = {
            "entries": stats.get("entries"),
            "max": stats.get("max"),
            "enabled": stats.get("enabled"),
        }
        if slug:
            extra["slug"] = slug
        logger.debug(event, extra=extra)
    except Exception:
        # Mai bloccare chiamanti per telemetria accessoria
        pass


def clear_frontmatter_cache(path: Path | None = None) -> None:
    """Svuota la cache del frontmatter o invalida una singola entry.

    Usata anche dai workflow semantici (`semantic.api`) per isolare i run all'interno della stessa process.
    """

    _FRONTMATTER_CACHE.clear(path)


# -----------------------------
# Helpers
# -----------------------------


def _titleize(name: str) -> str:
    """Titolo leggibile da nome file/cartella."""
    parts = name.replace("_", " ").replace("-", " ").split()
    return " ".join(p.capitalize() for p in parts) if parts else name


def _ensure_safe(base_dir: Path, candidate: Path, *, slug: str | None = None) -> Path:
    """Path-safety SSoT: risolve e valida `candidate` entro `base_dir` in un'unica operazione.

    Delegato a `pipeline.path_utils.ensure_within_and_resolve` per evitare TOCTOU/symlink games
    e mantenere le eccezioni tipizzate della pipeline (es. PathTraversalError/ConfigError).
    """
    try:
        return cast(Path, ensure_within_and_resolve(base_dir, candidate))
    except PathTraversalError as exc:
        raise PathTraversalError(str(exc), slug=slug, file_path=str(candidate)) from exc


def _sorted_pdfs(cat_dir: Path) -> list[Path]:
    # Nota: filtrato a valle in _filter_safe_pdfs (per base/raw_root)
    return sorted(
        iter_safe_paths(cat_dir, include_dirs=False, include_files=True, suffixes=(".pdf",)),
        key=lambda p: p.relative_to(cat_dir).as_posix().lower(),
    )


def _relative_to(base: Path, candidate: Path) -> str:
    try:
        return str(candidate.relative_to(base))
    except Exception:
        return str(candidate)


def _run_id_from_logger(logger: logging.Logger) -> str | None:
    ctx = getattr(logger, "_logging_ctx_view", None)
    if ctx is None:
        return None
    return getattr(ctx, "run_id", None)


def _filter_safe_pdfs(
    base_dir: Path,
    raw_root: Path,
    pdfs: Iterable[Path],
    *,
    slug: str | None = None,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Applica path-safety per-file e scarta symlink o path fuori perimetro.

    Mantiene l'ordinamento ricevuto.
    """
    log = logger or get_structured_logger("pipeline.content_utils")
    out: list[Path] = []
    run_id = _run_id_from_logger(log)
    for p in pdfs:
        try:
            if p.is_symlink():
                with start_decision_span(
                    "filter",
                    slug=slug,
                    run_id=run_id,
                    trace_kind="onboarding",
                    phase="semantic.discover_raw",
                    file_path_relative=_relative_to(raw_root, p),
                    decision_channel="auto",
                    risk_level="high",
                    attributes={
                        "reason": "symlink",
                        "status": "blocked",
                        "policy_id": "INGEST.SAFE_PATH",
                    },
                ):
                    log.warning(
                        "pipeline.content.skip_symlink",
                        extra={"slug": slug, "file_path": str(p)},
                    )
                continue
            safe_p = ensure_within_and_resolve(raw_root, p)
        except Exception as e:  # pragma: no cover (error path)
            with start_decision_span(
                "filter",
                slug=slug,
                run_id=run_id,
                trace_kind="onboarding",
                phase="semantic.discover_raw",
                file_path_relative=_relative_to(raw_root, p),
                decision_channel="auto",
                risk_level="high",
                attributes={
                    "reason": "unsafe_path",
                    "status": "blocked",
                    "error": str(e),
                    "policy_id": "INGEST.SAFE_PATH",
                },
            ):
                log.warning(
                    "pipeline.content.skip_unsafe",
                    extra={"slug": slug, "file_path": str(p), "error": str(e)},
                )
            continue
        out.append(safe_p)
    return out


def _dump_frontmatter(meta: dict[str, Any]) -> str:  # compat wrapper
    meta_dict: dict[str, Any] = dict(meta)
    return cast(str, _shared_dump_frontmatter(meta_dict))


def _normalize_excerpt(text: str) -> str:
    """Riduce whitespace e newline del testo estratto."""
    cleaned = re.sub(r"\s+", " ", text or "")
    return cleaned.strip()


def _extract_pdf_text(
    pdf_path: Path,
    *,
    slug: str | None,
    logger: logging.Logger,
) -> str:
    """Legge tutto il testo dal PDF (normalized) con hard-fail su errori."""
    try:
        from nlp.nlp_keywords import extract_text_from_pdf
    except Exception as exc:  # pragma: no cover - dependency error
        raise PipelineError(
            "PDF extractor dependency missing: nlp.nlp_keywords.extract_text_from_pdf not available.",
            slug=slug,
            file_path=str(pdf_path),
        ) from exc

    try:
        raw_text = extract_text_from_pdf(str(pdf_path))
    except Exception as exc:
        raise PipelineError(
            "PDF text extraction failed.",
            slug=slug,
            file_path=str(pdf_path),
        ) from exc

    normalized = _normalize_excerpt(raw_text)
    if not normalized:
        raise PipelineError(
            "PDF text extraction returned empty content.",
            slug=slug,
            file_path=str(pdf_path),
        )
    return normalized


def _chunk_pdf_text(text: str, *, chunk_chars: int = 1200, max_chunks: int = 4) -> list[str]:
    """Divide un testo in chunk di lunghezza massima `chunk_chars`."""
    if not text:
        return []
    out: list[str] = []
    total = len(text)
    for idx in range(0, total, chunk_chars):
        if len(out) >= max_chunks:
            break
        chunk = text[idx : idx + chunk_chars].strip()
        if chunk:
            out.append(chunk)
    return out


def _build_chunk_summaries(chunks: list[str], *, max_chars: int = _PDF_EXCERPT_MAX_CHARS) -> list[str]:
    summaries: list[str] = []
    for chunk in chunks:
        if len(summaries) >= 4:
            break
        snippet = chunk[:max_chars]
        if len(chunk) > max_chars:
            snippet = snippet.rstrip() + "..."
        summaries.append(snippet)
    return summaries


def _extract_pdf_excerpt(
    pdf_path: Path,
    *,
    slug: str | None,
    logger: logging.Logger,
    text: str | None = None,
    max_chars: int = _PDF_EXCERPT_MAX_CHARS,
) -> str:
    """Restituisce il testo pulito (max_chars) estratto da un PDF (hard-fail su errori)."""
    if not text:
        text = _extract_pdf_text(pdf_path, slug=slug, logger=logger)
    excerpt = text[:max_chars].rstrip()
    if len(text) > max_chars:
        excerpt += "..."
    return excerpt


def _write_markdown_for_pdf(
    pdf_path: Path,
    raw_root: Path,
    target_root: Path,
    candidates: Mapping[str, Mapping[str, Any]],
    cfg: SemanticConfig,
    *,
    slug: str | None = None,
) -> Path:
    """Genera un file Markdown 1:1 per il PDF indicato, includendo frontmatter completo."""
    rel_pdf = pdf_path.relative_to(raw_root)
    md_candidate = target_root / rel_pdf.with_suffix(".md")
    md_path = cast(Path, ensure_within_and_resolve(target_root, md_candidate))
    md_path.parent.mkdir(parents=True, exist_ok=True)

    candidate_meta = candidates.get(rel_pdf.as_posix(), {}) if candidates else {}
    tags_raw = candidate_meta.get("tags") or []
    tags_sorted = sorted({str(t).strip() for t in tags_raw if str(t).strip()})
    logger = get_structured_logger("pipeline.content_utils", context={"slug": slug})
    text = _extract_pdf_text(pdf_path, slug=slug, logger=logger)
    excerpt = _extract_pdf_excerpt(pdf_path, slug=slug, logger=logger, text=text)
    chunks = _chunk_pdf_text(text, chunk_chars=900, max_chunks=4)
    chunk_summaries = _build_chunk_summaries(chunks)
    body_parts: list[str] = []
    if excerpt:
        body_parts.append(excerpt)
    for idx, chunk in enumerate(chunks):
        body_parts.append(f"### Chunk {idx + 1}\n{chunk}")
    body_parts.append(f"*Documento sincronizzato da `{rel_pdf.as_posix()}`.*")
    body = "\n\n".join(body_parts).rstrip()
    body += "\n"

    existing_created_at: str | None = None
    existing_meta: dict[str, Any] = {}
    if md_path.exists():
        try:
            try:
                stat = md_path.stat()
                cache_key = (md_path, stat.st_mtime_ns, stat.st_size)
            except OSError:
                cache_key = None
            cached_entry: tuple[dict[str, Any], str] | None = _FRONTMATTER_CACHE.get(cache_key) if cache_key else None
            if cached_entry:
                existing_meta, body_prev = cached_entry
            else:
                existing_meta, body_prev = read_frontmatter(target_root, md_path, use_cache=False)
                if cache_key:
                    _FRONTMATTER_CACHE.set(cache_key, (existing_meta, body_prev))
            existing_created_at = str(existing_meta.get("created_at") or "").strip() or None
            if body_prev.strip() == body.strip() and existing_meta.get("tags_raw") == tags_sorted:
                return md_path
        except (OSError, PipelineError) as exc:
            logger.warning(
                "pipeline.content.frontmatter_read_failed",
                extra={"slug": slug, "path": str(md_path), "error": str(exc)},
            )
            existing_created_at = None
            existing_meta = {}

    meta: dict[str, Any] = {
        "title": _titleize(pdf_path.stem),
        "source_category": rel_pdf.parent.as_posix() or None,
        "source_file": rel_pdf.name,
        "created_at": existing_created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tags_raw": tags_sorted,
    }
    for key, value in existing_meta.items():
        if key not in meta:
            meta[key] = value
    if excerpt:
        meta["excerpt"] = excerpt
    elif existing_meta.get("excerpt"):
        meta["excerpt"] = existing_meta["excerpt"]
    if chunk_summaries:
        meta["content_chunks"] = chunk_summaries
    elif existing_meta.get("content_chunks"):
        meta["content_chunks"] = existing_meta["content_chunks"]
    safe_write_text(md_path, _dump_frontmatter(meta) + body, encoding="utf-8", atomic=True)

    # Aggiorna la cache locale del frontmatter con il nuovo contenuto scritto
    try:
        stat = md_path.stat()
        cache_key = (md_path, stat.st_mtime_ns, stat.st_size)
        _FRONTMATTER_CACHE.set(cache_key, (meta, body))
    except OSError:
        pass
    return md_path


def _group_safe_pdfs_by_category(
    raw_root: Path,
    safe_pdfs: list[Path],
) -> tuple[list[Path], CategoryGroups]:
    """Dato un elenco di PDF *già* validati (risolti dentro raw_root),
    restituisce:
      - (root_pdfs, [(cat_dir, pdfs_in_cat), ...]) con cat_dir = directory immediata sotto raw_root.
    """
    root_pdfs = [p for p in safe_pdfs if p.parent == raw_root]
    groups: dict[Path, list[Path]] = {}
    for pdf in safe_pdfs:
        try:
            rel = pdf.relative_to(raw_root)
        except Exception:
            continue
        parts = list(rel.parts)
        if len(parts) < 2:
            continue
        cat_dir = raw_root / parts[0]
        groups.setdefault(cat_dir, []).append(pdf)

    items: list[tuple[Path, list[Path]]] = []
    for cat_dir in sorted(groups.keys(), key=lambda d: d.name.lower()):
        items.append((cat_dir, sorted(groups[cat_dir], key=lambda p: p.as_posix().lower())))
    return (sorted(root_pdfs, key=lambda p: p.as_posix().lower()), items)


def _iter_category_pdfs(raw_root: Path) -> list[tuple[Path, list[Path]]]:
    """Restituisce le categorie immediate e la lista dei PDF (ricorsiva) per ciascuna applicando path-safety."""
    logger = get_structured_logger("pipeline.content_utils")

    def _on_skip(path: Path, reason: str) -> None:
        with start_decision_span(
            "filter",
            slug=None,
            run_id=_run_id_from_logger(logger),
            trace_kind="onboarding",
            phase="semantic.auto_tagger",
            attributes={
                "decision_type": "filter",
                "file_path_relative": _relative_to(raw_root, path),
                "reason": reason,
                "status": "blocked",
            },
        ):
            logger.warning("pipeline.content.skip_unsafe", extra={"file_path": str(path), "reason": reason})

    out: list[tuple[Path, list[Path]]] = []
    for cat_dir in iter_safe_paths(raw_root, include_dirs=True, include_files=False, on_skip=_on_skip):
        out.append((cat_dir, _sorted_pdfs(cat_dir)))
    return out


def _discover_safe_pdfs(
    raw_root: Path,
    *,
    base_dir: Path,
    slug: str | None = None,
    logger: logging.Logger | None = None,
) -> tuple[list[Path], CategoryGroups]:
    """Discovery centralizzata dei PDF in RAW con path-safety e logging skip symlink/traversal."""
    logger = logger or get_structured_logger("pipeline.content_utils")

    def _on_skip(path: Path, reason: str) -> None:
        event = "pipeline.content.skip_symlink" if reason == "symlink" else "pipeline.content.skip_unsafe"
        logger.warning(event, extra={"slug": slug, "file_path": str(path), "reason": reason})

    root_candidates = iter_safe_paths(
        raw_root,
        include_dirs=False,
        include_files=True,
        suffixes=(".pdf",),
        on_skip=_on_skip,
    )
    root_pdfs = _filter_safe_pdfs(
        base_dir,
        raw_root,
        sorted(root_candidates, key=lambda p: p.name.lower()),
        slug=slug,
        logger=logger,
    )
    cat_items = _iter_category_pdfs(raw_root)
    return root_pdfs, cat_items


def _plan_pdf_groups(
    *,
    base_dir: Path,
    raw_root: Path,
    safe_pdfs: list[Path] | None,
    slug: str | None,
    logger: logging.Logger,
) -> tuple[list[Path], CategoryGroups]:
    """Determina l'elenco dei PDF root e di categoria, rispettando eventuali safe_pdfs prevalidate."""
    if safe_pdfs is not None:
        return _group_safe_pdfs_by_category(raw_root, safe_pdfs)
    return _discover_safe_pdfs(
        raw_root,
        base_dir=base_dir,
        slug=slug,
        logger=logger,
    )


def _cleanup_orphan_markdown(
    target: Path,
    written: set[Path],
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Rimuove i markdown non piu associati ai PDF, preservando README/SUMMARY."""
    log = logger or get_structured_logger("pipeline.content_utils")
    removed = 0
    for candidate in iter_safe_paths(target, include_dirs=False, include_files=True, suffixes=(".md",)):
        low = candidate.name.lower()
        if low in {"readme.md", "summary.md"}:
            continue
        if candidate not in written:
            ensure_within(target, candidate)
            try:
                candidate.unlink(missing_ok=True)
                removed += 1
            except TypeError:
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    continue
                else:
                    removed += 1
    if removed > 0:
        try:
            log.info(
                "pipeline.content.orphan_deleted",
                extra={"path": str(target), "count": int(removed)},
            )
        except Exception:
            pass


# -----------------------------
# API
# -----------------------------


def validate_markdown_dir(ctx: _ClientCtx, book_dir: Path | None = None) -> Path:
    """Verifica che la cartella markdown esista, sia una directory e sia 'safe' rispetto a ctx.repo_root_dir."""
    target_input: Path = book_dir if book_dir is not None else ctx.book_dir
    target = _ensure_safe(ctx.repo_root_dir, target_input, slug=getattr(ctx, "slug", None))

    if not target.exists():
        raise PipelineError(
            f"Markdown directory does not exist: {target}",
            slug=getattr(ctx, "slug", None),
            file_path=str(target),
        )
    if not target.is_dir():
        raise PipelineError(
            f"Markdown path is not a directory: {target}",
            slug=getattr(ctx, "slug", None),
            file_path=str(target),
        )
    return target


def generate_readme_markdown(ctx: _ReadmeCtx, book_dir: Path | None = None) -> Path:
    """Crea (o sovrascrive) README.md nella cartella markdown target."""
    layout = WorkspaceLayout.from_context(ctx)  # type: ignore[arg-type]
    paths = resolve_context_paths(layout)
    repo_root_dir = paths.repo_root_dir
    default_book_dir = paths.book_dir
    target_input: Path = book_dir if book_dir is not None else default_book_dir
    target = _ensure_safe(repo_root_dir, target_input, slug=getattr(ctx, "slug", None))
    target.mkdir(parents=True, exist_ok=True)

    title = getattr(ctx, "slug", None) or "Knowledge Base"
    readme = target / "README.md"

    sections: list[str] = []
    sections.append(
        (
            "## Come preparare i documenti per l'onboarding\n\n"
            "1. Leggi il Vision Statement: e' il contratto semantico tra la tua organizzazione e il sistema.\n"
            "2. Associa ogni documento a un'entita (es. Progetto, Organizzazione, Contratto, Decisione).\n"
            "3. Rinomina i file anteponendo un codice di 3-4 lettere (prefisso) seguito da un trattino.\n\n"
            "Esempi:\n"
            "- `PRJ-Progetto_Sviluppo_AI_2025.pdf` -> entita: Progetto (operativo)\n"
            "- `ORG-Statuto_NeXT_srl.pdf` -> entita: Organizzazione (attore)\n"
            "- `CTR-Contratto_servizi_Cloud_ClienteX.pdf` -> entita: Contratto (oggetto)\n"
            "- `DEC-Verbale_CDA_2025-01-15.pdf` -> entita: Decisione (azione)\n\n"
            "Questi codici collegano i documenti alle entita del modello ER e migliorano tagging, layout ed embedding."
        )
    )
    sections.append(
        (
            "## Entita fondamentali (estratto)\n\n"
            "- Operativi: Progetto, Obiettivo, Milestone, Epic, Task, Processo, Deliverable\n"
            "- Attori: Organizzazione, Cliente, Stakeholder, Team, Operatore, Decisore, Management, Fornitore\n"
            "- Azioni: Decisione, Analisi, Modifica, Intervento, Upgrade, Downgrade, Validazione\n"
            "- Oggetti: Bene, Servizio, Skill, Risorsa, Esternalizzazione, Documento, Contratto, Dataset\n\n"
            "Il modello ER deriva dal Vision Statement: se cambia la struttura o le entita, "
            "aggiorna il Vision e rigenera la run Vision."
        )
    )
    logger = get_structured_logger("pipeline.content_utils")
    try:
        cfg = load_semantic_config(ctx.repo_root_dir)
        areas_data = cfg.mapping.get("areas") if isinstance(cfg.mapping, dict) else None
        iterable: Iterable[tuple[str, Any]]
        if isinstance(areas_data, dict):
            iterable = list(areas_data.items())
        elif isinstance(areas_data, list):
            iterable = [
                (
                    str(item.get("key") or item.get("name") or f"area_{idx}"),
                    item,
                )
                for idx, item in enumerate(areas_data)
                if isinstance(item, dict)
            ]
        else:
            iterable = []
        for key, meta in iterable:
            display = _titleize(str(key))
            descr = str((meta or {}).get("descrizione") or "").strip()
            section_body = f"## {display}\n"
            if descr:
                section_body += f"\n{descr}\n"
            sections.append(section_body.strip())
    except Exception as exc:  # pragma: no cover - fallback path
        logger.warning(
            "pipeline.content.mapping_failed",
            extra={
                "slug": getattr(ctx, "slug", None),
                "error": str(exc),
            },
        )

    content = "\n\n".join(sections).strip() or "Contenuti generati/curati automaticamente."
    safe_write_text(
        readme,
        f"# {title}\n\n{content}\n",
        encoding="utf-8",
        atomic=True,
    )
    return readme


def generate_summary_markdown(ctx: _ReadmeCtx, book_dir: Path | None = None) -> Path:
    """Genera SUMMARY.md elencando i .md nella cartella target (escludendo README.md e SUMMARY.md)."""
    layout = WorkspaceLayout.from_context(ctx)  # type: ignore[arg-type]
    paths = resolve_context_paths(layout)
    repo_root_dir = paths.repo_root_dir
    default_book_dir = paths.book_dir
    target_input: Path = book_dir if book_dir is not None else default_book_dir
    target = _ensure_safe(repo_root_dir, target_input, slug=getattr(ctx, "slug", None))
    target.mkdir(parents=True, exist_ok=True)

    summary = target / "SUMMARY.md"
    lines: list[str] = ["# Summary", ""]

    def iter_markdown() -> Iterable[Path]:
        candidates = iter_safe_paths(target, include_dirs=False, include_files=True, suffixes=(".md",))
        for md in sorted(candidates, key=lambda p: p.relative_to(target).as_posix().lower()):
            name = md.name.lower()
            if name in {"readme.md", "summary.md"}:
                continue
            yield md.relative_to(target)

    emitted_headers: set[str] = set()
    for rel in iter_markdown():
        parts = list(rel.parts)
        file_name = parts.pop()
        for depth, part in enumerate(parts):
            key = "/".join(parts[: depth + 1])
            if key not in emitted_headers:
                indent = "    " * depth
                lines.append(f"{indent}- **{_titleize(part)}**")
                emitted_headers.add(key)
        indent = "    " * len(parts)
        lines.append(f"{indent}- [{_titleize(Path(file_name).stem)}]({quote(rel.as_posix())})")

    safe_write_text(summary, "\n".join(lines).rstrip() + "\n", encoding="utf-8", atomic=True)
    return summary


def convert_files_to_structured_markdown(
    ctx: _ClientCtx,
    book_dir: Path | None = None,
    *,
    safe_pdfs: list[Path] | None = None,
) -> None:
    """Converte i PDF in RAW in un set di .md strutturati nella cartella `book_dir`.

    Se `safe_pdfs` è fornito, **non** esegue alcuna discovery su disco e assume
    che la lista sia già validata e risolta all'interno di `ctx.raw_dir`.
    """
    base = ctx.repo_root_dir
    raw_root = ctx.raw_dir
    target_input: Path = book_dir if book_dir is not None else ctx.book_dir

    # sicurezza percorso per target e raw_root
    target = _ensure_safe(base, target_input, slug=getattr(ctx, "slug", None))
    raw_root = _ensure_safe(base, raw_root, slug=getattr(ctx, "slug", None))

    target.mkdir(parents=True, exist_ok=True)

    if not raw_root.exists():
        raise PipelineError(
            f"Raw directory does not exist: {raw_root}",
            slug=getattr(ctx, "slug", None),
            file_path=str(raw_root),
        )
    if not raw_root.is_dir():
        raise PipelineError(
            f"Raw path is not a directory: {raw_root}",
            slug=getattr(ctx, "slug", None),
            file_path=str(raw_root),
        )

    cfg = load_semantic_config(ctx.repo_root_dir)
    candidates = extract_semantic_candidates(raw_root, cfg)

    written: set[Path] = set()

    logger = get_structured_logger("pipeline.content_utils", context={"slug": getattr(ctx, "slug", None)})

    root_pdfs, cat_items = _plan_pdf_groups(
        base_dir=base,
        raw_root=raw_root,
        safe_pdfs=safe_pdfs,
        slug=getattr(ctx, "slug", None),
        logger=logger,
    )

    slug = getattr(ctx, "slug", None)
    for pdf in root_pdfs:
        written.add(_write_markdown_for_pdf(pdf, raw_root, target, candidates, cfg, slug=slug))

    for _cat_dir, pdfs in cat_items:
        safe_list = (
            pdfs
            if safe_pdfs is not None
            else _filter_safe_pdfs(
                base,
                raw_root,
                pdfs,
                slug=getattr(ctx, "slug", None),
                logger=logger,
            )
        )
        for pdf in safe_list:
            written.add(_write_markdown_for_pdf(pdf, raw_root, target, candidates, cfg, slug=slug))

    _cleanup_orphan_markdown(target, written, logger=logger)

    log_frontmatter_cache_stats(
        logger,
        slug=slug,
    )


def build_chunk_records_from_markdown_files(
    slug: str,
    md_paths: list[Path | str],
    *,
    created_at: str | None = None,
    chunking: Literal["file", "heading"] = "file",
    base_dir: Path | str | None = None,
) -> list[ChunkRecord]:
    """Costruisce ChunkRecord v0: un file markdown ► un chunk (indice 0)."""

    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    records: list[ChunkRecord] = []
    base_path = Path(base_dir) if base_dir is not None else None
    resolved_base = base_path.resolve() if base_path is not None else None
    for raw_path in md_paths:
        path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
        safe_path = path
        if resolved_base is not None:
            try:
                safe_path = ensure_within_and_resolve(resolved_base, path)
            except PathTraversalError as exc:
                raise PipelineError(
                    "Markdown path fuori perimetro.",
                    slug=slug,
                    file_path=str(path),
                ) from exc
        try:
            file_meta, body = read_frontmatter(safe_path.parent, safe_path, encoding="utf-8", use_cache=True)
            text = (body or "").lstrip("\ufeff")
        except Exception:
            file_meta = {}
            text = read_text_safe(safe_path.parent, safe_path, encoding="utf-8")
        source_path = _format_source_path(safe_path, resolved_base)

        if chunking == "heading":
            segments = _segment_markdown_by_heading(text)
            if not segments:
                segments = [(None, text)]
        elif chunking == "file":
            segments = [(None, text)]
        else:
            raise PipelineError(f"chunking mode '{chunking}' non supportato")

        for chunk_index, (layout_section, chunk_text) in enumerate(segments):
            payload = chunk_text.strip()
            if not payload:
                continue
            key = f"{slug}:{source_path}:{chunk_index}:{layout_section or ''}:{payload}"
            chunk_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
            metadata: dict[str, object] = dict(file_meta or {})
            if layout_section:
                metadata["layout_section"] = layout_section
            records.append(
                ChunkRecord(
                    id=chunk_id,
                    slug=slug,
                    source_path=source_path,
                    text=payload,
                    chunk_index=chunk_index,
                    created_at=timestamp,
                    metadata=metadata,
                )
            )
    return records


def _format_source_path(path: Path, base: Path | None) -> str:
    if base is None:
        return str(path)
    try:
        return path.resolve().relative_to(base).as_posix()
    except Exception:
        return str(path)


_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")


def _segment_markdown_by_heading(text: str) -> list[tuple[str | None, str]]:
    """Divide un markdown in chunk iniziando da ogni heading (#/##)."""

    lines = text.splitlines()
    chunks: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        match = _HEADING_PATTERN.match(stripped)
        if match:
            if current_lines:
                chunk_text = "\n".join(current_lines).strip()
                if chunk_text:
                    chunks.append((current_heading, chunk_text))
            current_heading = match.group(2).strip()
            current_lines = [line]
            continue
        current_lines.append(line)

    if current_lines:
        chunk_text = "\n".join(current_lines).strip()
        if chunk_text:
            chunks.append((current_heading, chunk_text))

    return chunks
