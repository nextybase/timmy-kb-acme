# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/api.py
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Sequence, TypeAlias, TypeVar, cast

from pipeline.constants import OUTPUT_DIR_NAME, REPO_NAME_PREFIX
from pipeline.exceptions import ConfigError, PathTraversalError
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, validate_slug
from semantic import embedding_service
from semantic.auto_tagger import extract_semantic_candidates as _extract_candidates
from semantic.auto_tagger import render_tags_csv as _render_tags_csv
from semantic.config import load_semantic_config as _load_semantic_config
from semantic.convert_service import convert_markdown
from semantic.embedding_service import list_content_markdown
from semantic.frontmatter_service import enrich_frontmatter, write_summary_and_readme
from semantic.normalizer import normalize_tags as _normalize_tags
from semantic.tags_extractor import copy_local_pdfs_to_raw as _copy_local_pdfs_to_raw
from semantic.tags_io import write_tagging_readme as _write_tagging_readme
from semantic.tags_io import write_tags_reviewed_from_nlp_db as _write_tags_yaml_from_db
from semantic.types import EmbeddingsClient as _EmbeddingsClient
from semantic.vocab_loader import load_reviewed_vocab as _load_reviewed_vocab
from storage.tags_store import DocEntityRecord
from storage.tags_store import derive_db_path_from_yaml_path as _derive_tags_db_path
from storage.tags_store import ensure_schema_v2 as _ensure_tags_schema_v2
from storage.tags_store import get_conn as _get_tags_conn
from storage.tags_store import save_doc_entities as _save_doc_entities

_T = TypeVar("_T")

if TYPE_CHECKING:
    from pipeline.context import ClientContext as ClientContextType
else:
    from semantic.types import ClientContextProtocol as ClientContextType

__all__ = [
    "get_paths",
    "load_reviewed_vocab",
    "require_reviewed_vocab",
    "convert_markdown",
    "enrich_frontmatter",
    "write_summary_and_readme",
    "build_tags_csv",
    "build_markdown_book",
    "index_markdown_to_db",
    "copy_local_pdfs_to_raw",
    "list_content_markdown",
    "export_tags_yaml_from_db",
]


def get_paths(slug: str) -> Dict[str, Path]:
    safe_slug = validate_slug(slug)
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{safe_slug}"
    return {
        "base": base_dir,
        "raw": base_dir / "raw",
        "book": base_dir / "book",
        "semantic": base_dir / "semantic",
    }


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Sequence[str]]]:
    return cast(Dict[str, Dict[str, Sequence[str]]], _load_reviewed_vocab(base_dir, logger))


def require_reviewed_vocab(base_dir: Path, logger: logging.Logger, *, slug: str) -> Dict[str, Dict[str, Sequence[str]]]:
    """Restituisce il vocabolario canonico e solleva ConfigError se mancante (fail-fast)."""
    return _require_reviewed_vocab(base_dir, logger, slug=slug)


def _require_reviewed_vocab(
    base_dir: Path,
    logger: logging.Logger,
    *,
    slug: str,
) -> Dict[str, Dict[str, Sequence[str]]]:
    """Restituisce il vocabolario canonico o solleva ConfigError se assente."""
    global _LAST_VOCAB_STUBBED
    vocab = load_reviewed_vocab(base_dir, logger)
    if vocab:
        _LAST_VOCAB_STUBBED = False
        return vocab
    loader_module = getattr(_load_reviewed_vocab, "__module__", "")
    if loader_module != "semantic.vocab_loader":
        _LAST_VOCAB_STUBBED = True
        raise ConfigError(
            "Vocabolario stub: rigenera semantic/tags.db prima di procedere.",
            slug=slug,
            file_path=base_dir / "semantic" / "tags.db",
        )
    _LAST_VOCAB_STUBBED = False
    tags_db = Path(_derive_tags_db_path(base_dir / "semantic" / "tags_reviewed.yaml"))
    raise ConfigError(
        "Vocabolario canonico assente. Esegui l'estrazione tag per popolare semantic/tags.db.",
        slug=slug,
        file_path=tags_db,
    )


_LAST_VOCAB_STUBBED = False

BuildWorkflowResult: TypeAlias = tuple[Path, list[Path], list[Path]]


def _collect_doc_entities(candidates: Mapping[str, Mapping[str, Any]]) -> List[DocEntityRecord]:
    """Estrae le entity NLP dai metadati dei candidati in una lista flat."""

    doc_entities: List[DocEntityRecord] = []
    for rel_path, meta in candidates.items():
        sources = cast(Mapping[str, Any], meta.get("sources") or {})
        spacy_src = cast(Mapping[str, Any], sources.get("spacy") or {})
        areas = cast(Mapping[str, Sequence[str]], spacy_src.get("areas") or {})
        score_map = cast(Mapping[str, Any], meta.get("score") or {})
        rel_uid = Path(rel_path).as_posix()
        for area_key, ent_list in areas.items():
            for entity_id in ent_list or []:
                key = f"{area_key}:{entity_id}"
                try:
                    confidence = float(score_map.get(key, 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0
                if confidence <= 0.0:
                    continue
                doc_entities.append(
                    DocEntityRecord(
                        doc_uid=rel_uid,
                        area_key=str(area_key),
                        entity_id=str(entity_id),
                        confidence=confidence,
                        origin="spacy",
                        status="suggested",
                    )
                )
    return doc_entities


def _load_folder_terms(tags_db_path: Path) -> Dict[str, List[str]]:
    """Ritorna i top-term per cartella dal DB NLP (se presente)."""

    folder_terms: Dict[str, List[str]] = {}
    if not tags_db_path.exists():
        return folder_terms

    _ensure_tags_schema_v2(str(tags_db_path))
    with _get_tags_conn(str(tags_db_path)) as conn:
        rows = conn.execute(
            """
            SELECT f.path AS folder_path, t.canonical AS term, SUM(ft.weight) AS weight
            FROM folder_terms ft
            JOIN folders f ON f.id = ft.folder_id
            JOIN terms   t ON t.id = ft.term_id
            GROUP BY f.path, t.canonical
            ORDER BY f.path, weight DESC
            """
        ).fetchall()
    for row in rows:
        folder_path = str(row["folder_path"] or "")
        canonical = str(row["term"] or "").strip()
        if not canonical:
            continue
        rel_folder = folder_path[4:] if folder_path.startswith("raw/") else folder_path
        rel_folder = rel_folder.strip("/")
        folder_terms.setdefault(rel_folder, []).append(canonical)
    return folder_terms


def _apply_folder_terms(
    candidates: Dict[str, Dict[str, Any]],
    folder_terms: Mapping[str, Sequence[str]],
) -> None:
    """Arricchisce i metadati candidati con i top-term per cartella (in-place)."""

    for rel_path, meta in candidates.items():
        rel_folder = Path(rel_path).parent.as_posix()
        rel_folder = "" if rel_folder == "." else rel_folder
        nlp_tags = folder_terms.get(rel_folder)
        if not nlp_tags:
            continue
        existing = list(meta.get("tags") or [])
        seen_lower = {str(tag).strip().lower() for tag in existing if str(tag).strip()}
        enriched: list[str] = list(existing)
        for term in nlp_tags:
            term_norm = str(term).strip()
            if not term_norm:
                continue
            key = term_norm.lower()
            if key in seen_lower:
                continue
            enriched.append(term_norm)
            seen_lower.add(key)
            if len(enriched) >= 16:
                break
        if enriched:
            meta["tags"] = enriched


def build_tags_csv(context: ClientContextType, logger: logging.Logger, *, slug: str) -> Path:
    """Costruisce `tags_raw.csv` dal workspace corrente applicando arricchimento NLP (DB + Spacy)."""
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    raw_dir = cast(Path, getattr(context, "raw_dir", None) or paths["raw"])
    semantic_dir = base_dir / "semantic"
    csv_path = semantic_dir / "tags_raw.csv"

    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, semantic_dir)
    ensure_within(semantic_dir, csv_path)

    with phase_scope(logger, stage="build_tags_csv", customer=slug) as m:
        semantic_dir.mkdir(parents=True, exist_ok=True)
        cfg = _load_semantic_config(base_dir)
        candidates = _extract_candidates(raw_dir, cfg)
        candidates = _normalize_tags(candidates, cfg.mapping)
        doc_entities = _collect_doc_entities(candidates)

        # Arricchimento con top-terms NLP (se disponibili in tags.db)
        try:
            tags_db_path = Path(_derive_tags_db_path(semantic_dir / "tags_reviewed.yaml"))
            tags_db_path = ensure_within_and_resolve(semantic_dir, tags_db_path)
            folder_terms = _load_folder_terms(tags_db_path)
            if folder_terms:
                _apply_folder_terms(candidates, folder_terms)
            if doc_entities:
                _save_doc_entities(tags_db_path, doc_entities)
        except PathTraversalError:
            raise
        except Exception as exc:
            logger.exception(
                "semantic.tags_csv.enrichment_failed",
                extra={"slug": slug, "error": str(exc), "tags_db": str(tags_db_path)},
            )
            raise ConfigError("Arricchimento tag fallito", slug=slug) from exc

        _render_tags_csv(candidates, csv_path, base_dir=base_dir)
        count = len(candidates)
        logger.info(
            "semantic.tags_csv.built",
            extra={"slug": slug, "file_path": str(csv_path), "count": count},
        )
        _write_tagging_readme(semantic_dir, logger)
        try:
            m.set_artifacts(count)
        except Exception as exc:
            logger.warning("semantic.tags_csv.artifacts_missing", extra={"slug": slug, "error": str(exc)})
            m.set_artifacts(None)
    return csv_path


def export_tags_yaml_from_db(
    semantic_dir: Path,
    db_path: Path,
    logger: logging.Logger,
    *,
    workspace_base: Path | None = None,
    limit: int = 200,
    min_weight: float = 0.0,
    keep_only_listed: bool = True,
    version: str = "2",
) -> Path:
    """Facade sicuro per esportare tags_reviewed.yaml dal DB NLP (UI-only).
    Il parametro `workspace_base` filtra il perimetro root (default = semantic_dir.parent.parent)."""
    base_root_path = Path(workspace_base or Path(semantic_dir).parent.parent).resolve()
    semantic_dir_path = ensure_within_and_resolve(base_root_path, Path(semantic_dir))
    yaml_path = ensure_within_and_resolve(semantic_dir_path, semantic_dir_path / "tags_reviewed.yaml")
    expected_db_path = ensure_within_and_resolve(
        semantic_dir_path,
        Path(_derive_tags_db_path(yaml_path)),
    )
    actual_db_path = ensure_within_and_resolve(base_root_path, Path(db_path))
    if actual_db_path != expected_db_path:
        raise ConfigError(
            "Percorso DB non coerente con la directory semantic specificata.",
            file_path=str(actual_db_path),
        )
    result = _write_tags_yaml_from_db(
        semantic_dir_path,
        expected_db_path,
        logger,
        limit=limit,
        min_weight=min_weight,
        keep_only_listed=keep_only_listed,
        version=version,
    )
    return cast(Path, result)


def copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger: logging.Logger) -> int:
    """Copia PDF locali in raw/ rispettando path-safety, restituisce il conteggio copiato."""
    return int(_copy_local_pdfs_to_raw(src_dir, raw_dir, logger))


def _run_build_workflow(
    context: ClientContextType,
    logger: logging.Logger,
    *,
    slug: str,
    stage_wrapper: Callable[[str, Callable[[], _T]], _T] | None = None,
    convert_fn: Callable[[ClientContextType, logging.Logger, str], List[Path]] | None = None,
    vocab_fn: Callable[[Path, logging.Logger, str], Dict[str, Dict[str, set[str]]]] | None = None,
    enrich_fn: (
        Callable[[ClientContextType, logging.Logger, Dict[str, Dict[str, set[str]]], str], list[Path]] | None
    ) = None,
    summary_fn: Callable[[ClientContextType, logging.Logger, str], object] | None = None,
) -> BuildWorkflowResult:
    """Esegue convert -> enrich -> summary/readme restituendo base_dir, mds e arricchiti."""

    ctx_base = cast(Path, getattr(context, "base_dir", None))
    base_dir = ctx_base if ctx_base is not None else get_paths(slug)["base"]

    def _wrap(stage_name: str, func: Callable[[], _T]) -> _T:
        if stage_wrapper is None:
            return func()
        return stage_wrapper(stage_name, func)

    convert_impl = convert_fn or convert_markdown
    vocab_impl = vocab_fn or _require_reviewed_vocab
    enrich_impl = enrich_fn or enrich_frontmatter
    summary_impl = summary_fn or write_summary_and_readme

    if convert_fn is None:
        mds = cast(List[Path], _wrap("convert_markdown", lambda: convert_impl(context, logger, slug=slug)))
    else:
        mds = cast(List[Path], _wrap("convert_markdown", lambda: convert_impl(context, logger, slug)))

    if vocab_fn is None:
        vocab = _wrap("require_reviewed_vocab", lambda: vocab_impl(base_dir, logger, slug=slug))
    else:
        vocab = _wrap("require_reviewed_vocab", lambda: vocab_impl(base_dir, logger, slug))

    if enrich_fn is None:
        touched = _wrap("enrich_frontmatter", lambda: enrich_impl(context, logger, vocab, slug=slug))
    else:
        touched = _wrap("enrich_frontmatter", lambda: enrich_impl(context, logger, vocab, slug))
    try:
        logger.info(
            "semantic.book.frontmatter",
            extra={"slug": slug, "enriched": len(cast(list, touched))},
        )
    except Exception as exc:
        logger.warning(
            "semantic.book.frontmatter",
            extra={"slug": slug, "enriched": None, "error": str(exc)},
        )
    if summary_fn is None:
        _wrap("write_summary_and_readme", lambda: summary_impl(context, logger, slug=slug))
    else:
        _wrap("write_summary_and_readme", lambda: summary_impl(context, logger, slug))
    return base_dir, mds, cast(list[Path], touched)


def build_markdown_book(context: ClientContextType, logger: logging.Logger, *, slug: str) -> list[Path]:
    """Fase unica che copre conversione, summary/readme e arricchimento frontmatter."""
    if logger is None:
        logger = get_structured_logger("semantic.book", context={"slug": slug})
    start_ts = time.perf_counter()
    with phase_scope(logger, stage="build_markdown_book", customer=slug) as m:
        _base_dir, mds, touched = _run_build_workflow(context, logger, slug=slug, stage_wrapper=None)
        try:
            # Artifacts = numero di MD di contenuto (coerente con convert_markdown)
            m.set_artifacts(len(mds))
        except Exception as exc:
            logger.warning("semantic.book.artifacts_missing", extra={"slug": slug, "error": str(exc)})
            m.set_artifacts(None)
    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "semantic.book.done",
        extra={
            "slug": slug,
            "ms": ms,
            "artifacts": {"content_files": len(mds)},
            "enriched_files": len(cast(list, touched)),
        },
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
    """Indice i Markdown presenti in book/ nel DB, delegando al servizio dedicato."""
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    book_dir = cast(Path, getattr(context, "md_dir", None) or paths["book"])
    return cast(
        int,
        embedding_service.index_markdown_to_db(
            base_dir=base_dir,
            book_dir=book_dir,
            slug=slug,
            logger=logger,
            scope=scope,
            embeddings_client=embeddings_client,
            db_path=db_path,
        ),
    )
