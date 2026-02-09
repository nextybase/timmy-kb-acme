# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/api.py
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Protocol, Sequence, TypeAlias, TypeVar, cast

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.types import ChunkRecord
from pipeline.workspace_layout import WorkspaceLayout
from semantic import embedding_service, tagging_service
from semantic.convert_service import convert_markdown
from semantic.embedding_service import list_content_markdown
from semantic.frontmatter_service import enrich_frontmatter, write_summary_and_readme
from semantic.tags_extractor import copy_local_pdfs_to_raw as _copy_local_pdfs_to_raw
from semantic.tags_io import write_tags_reviewed_from_nlp_db as _write_tags_yaml_from_db
from semantic.types import EmbeddingsClient as _EmbeddingsClient
from semantic.vocab_loader import load_reviewed_vocab as _load_reviewed_vocab
from storage.kb_store import KbStore

_T = TypeVar("_T")


class ConvertStage(Protocol):
    def __call__(self, context: "ClientContextType", logger: logging.Logger, *, slug: str) -> list[Path]: ...


class VocabStage(Protocol):
    def __call__(
        self, repo_root_dir: Path, logger: logging.Logger, *, slug: str
    ) -> Dict[str, Dict[str, Sequence[str]]]: ...


class EnrichStage(Protocol):
    def __call__(
        self,
        context: "ClientContextType",
        logger: logging.Logger,
        vocab: Dict[str, Dict[str, Sequence[str]]],
        *,
        slug: str,
    ) -> list[Path]: ...


class SummaryStage(Protocol):
    def __call__(self, context: "ClientContextType", logger: logging.Logger, *, slug: str) -> object: ...


StageWrapper = Callable[[str, Callable[[], Any]], Any]

if TYPE_CHECKING:
    from pipeline.context import ClientContext as ClientContextType
else:
    from semantic.types import SemanticContextProtocol as ClientContextType

__all__ = [
    "get_paths",
    "load_reviewed_vocab",
    "require_reviewed_vocab",
    "convert_markdown",
    "enrich_frontmatter",
    "write_summary_and_readme",
    "run_semantic_pipeline",
    "run_semantic_pipeline_for_slug",
    "build_tags_csv",
    "build_markdown_book",
    "index_markdown_to_db",
    "copy_local_pdfs_to_raw",
    "list_content_markdown",
    "export_tags_yaml_from_db",
]


def get_paths(slug: str) -> Dict[str, Path]:
    if not slug or not slug.strip():
        raise ConfigError("Slug semantic vuoto o invalido per la risoluzione dei path.", slug=slug or None)
    layout = WorkspaceLayout.from_slug(slug=slug, require_drive_env=False)
    return {
        "base": layout.repo_root_dir,
        "raw": layout.raw_dir,
        "normalized": layout.normalized_dir,
        "book": layout.book_dir,
        "semantic": layout.semantic_dir,
    }


def load_reviewed_vocab(
    repo_root_dir: Path, logger: logging.Logger, *, slug: str | None = None
) -> Dict[str, Dict[str, Sequence[str]]]:
    return cast(Dict[str, Dict[str, Sequence[str]]], _load_reviewed_vocab(repo_root_dir, logger, slug=slug))


def require_reviewed_vocab(
    repo_root_dir: Path, logger: logging.Logger, *, slug: str
) -> Dict[str, Dict[str, Sequence[str]]]:
    """Restituisce il vocabolario canonico e solleva ConfigError se mancante (fail-fast)."""
    return _require_reviewed_vocab(repo_root_dir, logger, slug=slug)


def _require_reviewed_vocab(
    repo_root_dir: Path,
    logger: logging.Logger,
    *,
    slug: str,
) -> Dict[str, Dict[str, Sequence[str]]]:
    """Restituisce il vocabolario canonico o solleva ConfigError se assente (fail-fast)."""
    vocab = load_reviewed_vocab(repo_root_dir, logger, slug=slug)
    if vocab:
        return vocab
    layout = WorkspaceLayout.from_workspace(repo_root_dir, slug=slug)
    tags_db = layout.semantic_dir / "tags.db"
    raise ConfigError(
        "Vocabolario canonico assente. Esegui l'estrazione tag per popolare semantic/tags.db.",
        slug=slug,
        file_path=tags_db,
    )


BuildWorkflowResult: TypeAlias = tuple[Path, list[Path], list[Path]]


def _extract_candidates(raw_dir: Path, cfg: object) -> Dict[str, Dict[str, object]]:
    """Private seam per test/patching: delega al motore di estrazione candidato."""
    from semantic.auto_tagger import extract_semantic_candidates

    return cast(Dict[str, Dict[str, object]], extract_semantic_candidates(raw_dir, cfg))


def build_tags_csv(context: ClientContextType, logger: logging.Logger, *, slug: str) -> Path:
    """Costruisce `tags_raw.csv` dal workspace corrente applicando arricchimento NLP (DB + Spacy)."""
    return tagging_service.build_tags_csv(context, logger, slug=slug)


def export_tags_yaml_from_db(
    semantic_dir: Path,
    db_path: Path,
    logger: logging.Logger,
    *,
    context: ClientContextType | None = None,
    workspace_base: Path | None = None,
    slug: str | None = None,
    limit: int = 200,
    min_weight: float = 0.0,
    keep_only_listed: bool = True,
    version: str = "2",
) -> Path:
    """Facade sicuro per esportare tags_reviewed.yaml dal DB NLP (UI-only).
    Richiede `context` o `workspace_base` canonico per risolvere il layout."""
    if context is not None:
        if getattr(context, "repo_root_dir", None) is None:
            raise ConfigError(
                "Contesto privo di repo_root_dir: impossibile risolvere il workspace.",
                file_path=str(semantic_dir),
            )
        layout = WorkspaceLayout.from_context(cast(Any, context))
    elif workspace_base is not None:
        if slug is None:
            raise ConfigError(
                "Slug richiesto per esportare tags_reviewed.yaml dal workspace base.",
                file_path=str(semantic_dir),
            )
        layout = WorkspaceLayout.from_workspace(Path(workspace_base).resolve(), slug=slug)
    else:
        raise ConfigError(
            "workspace_base o context richiesti per esportare tags_reviewed.yaml.",
            file_path=str(semantic_dir),
        )

    repo_root_dir = layout.repo_root_dir
    perimeter_root = repo_root_dir
    semantic_dir_path = ensure_within_and_resolve(perimeter_root, Path(semantic_dir))
    if semantic_dir_path != layout.semantic_dir:
        raise ConfigError(
            "semantic_dir non coerente con il workspace canonico.",
            file_path=str(semantic_dir_path),
        )
    expected_db_path = ensure_within_and_resolve(semantic_dir_path, semantic_dir_path / "tags.db")
    actual_db_path = ensure_within_and_resolve(perimeter_root, Path(db_path))
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


def _log_frontmatter_cache_failure(
    logger: logging.Logger,
    *,
    slug: str,
    context: ClientContextType,
    operation: str,
    exc: Exception,
) -> None:
    """Emit structured warning when the frontmatter cache cannot be cleared."""
    extra: dict[str, object | None] = {
        "slug": slug,
        "service_only": True,
        "service": "semantic.frontmatter_cache",
        "operation": operation,
        "error": str(exc),
        "error_type": type(exc).__name__,
    }
    run_id = getattr(context, "run_id", None)
    if run_id:
        extra["run_id"] = run_id
    try:
        logger.warning("semantic.frontmatter_cache.clear_failed", extra=extra)
    except Exception:
        logger.warning(
            "semantic.frontmatter_cache.clear_failed",
            extra={
                "slug": slug,
                "service_only": True,
                "service": "semantic.frontmatter_cache",
                "operation": operation,
                "error": "log emission failed",
            },
        )


def _run_build_workflow(
    context: ClientContextType,
    logger: logging.Logger,
    *,
    slug: str,
    stage_wrapper: StageWrapper | None = None,
    convert_fn: ConvertStage | None = None,
    vocab_fn: VocabStage | None = None,
    enrich_fn: EnrichStage | None = None,
    summary_fn: SummaryStage | None = None,
) -> BuildWorkflowResult:
    """Esegue convert -> enrich -> summary/readme restituendo repo_root_dir, mds e arricchiti.

    Durante il run usa la cache LRU del frontmatter (gestita da `pipeline.content_utils`) per
    velocizzare le riletture; al termine svuota sempre la cache con `clear_frontmatter_cache()`
    per evitare cross-contaminazione tra run consecutivi nella stessa process e rilasciare memoria.
    """

    if getattr(context, "repo_root_dir", None) is None:
        raise ConfigError(
            "Contesto privo di repo_root_dir: impossibile risolvere il workspace in modo deterministico.",
            slug=slug,
        )
    layout = WorkspaceLayout.from_context(cast(Any, context))
    repo_root_dir = layout.repo_root_dir

    def _wrap(stage_name: str, func: Callable[[], Any]) -> Any:
        if stage_wrapper is None:
            return func()
        return stage_wrapper(stage_name, func)

    convert_impl: ConvertStage = convert_fn or convert_markdown
    vocab_impl: VocabStage = vocab_fn or _require_reviewed_vocab
    enrich_impl: EnrichStage = enrich_fn or enrich_frontmatter
    summary_impl: SummaryStage = summary_fn or write_summary_and_readme

    try:
        mds: List[Path] = cast(
            List[Path],
            _wrap("convert_markdown", lambda: convert_impl(context, logger, slug=slug)),
        )

        vocab: Dict[str, Dict[str, Sequence[str]]] = cast(
            Dict[str, Dict[str, Sequence[str]]],
            _wrap("require_reviewed_vocab", lambda: vocab_impl(repo_root_dir, logger, slug=slug)),
        )

        touched: List[Path] = cast(
            List[Path],
            _wrap("enrich_frontmatter", lambda: enrich_impl(context, logger, vocab, slug=slug)),
        )
        try:
            logger.info(
                "semantic.book.frontmatter",
                extra={"slug": slug, "enriched": len(touched)},
            )
        except Exception as exc:
            logger.warning(
                "semantic.book.frontmatter",
                extra={"slug": slug, "enriched": None, "error": str(exc)},
            )
        _wrap("write_summary_and_readme", lambda: summary_impl(context, logger, slug=slug))
        return repo_root_dir, mds, touched
    finally:
        try:
            from pipeline.content_utils import clear_frontmatter_cache, log_frontmatter_cache_stats
        except Exception as exc:
            _log_frontmatter_cache_failure(
                logger,
                slug=slug,
                context=context,
                operation="import",
                exc=exc,
            )
            # Non interrompere il return della pipeline; log-only.
            return

        try:
            log_frontmatter_cache_stats(
                logger,
                "semantic.frontmatter_cache.stats_before_clear",
                slug=slug,
            )
        except Exception as exc:
            logger.warning(
                "semantic.frontmatter_cache.stats_log_failed",
                extra={
                    "slug": slug,
                    "service_only": True,
                    "service": "semantic.frontmatter_cache",
                    "operation": "stats",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "run_id": getattr(context, "run_id", None),
                },
            )

        try:
            clear_frontmatter_cache()
        except Exception as exc:
            _log_frontmatter_cache_failure(
                logger,
                slug=slug,
                context=context,
                operation="clear",
                exc=exc,
            )


def run_semantic_pipeline(
    context: ClientContextType,
    logger: logging.Logger,
    *,
    slug: str,
    stage_wrapper: StageWrapper | None = None,
) -> BuildWorkflowResult:
    """Esegue la pipeline semantica standard esponendo un'API pubblica stabile.

    Usa la cache LRU del frontmatter durante il run e la svuota automaticamente a fine workflow
    per garantire isolamento tra esecuzioni consecutive.
    """

    return _run_build_workflow(
        context,
        logger,
        slug=slug,
        stage_wrapper=stage_wrapper,
        convert_fn=None,
        vocab_fn=None,
        enrich_fn=None,
        summary_fn=None,
    )


def run_semantic_pipeline_for_slug(
    slug: str,
    *,
    context_factory: Callable[[str], "ClientContextType"],
    logger: logging.Logger | None = None,
    gating: Callable[[str], tuple[str, bool, Path | None]] | None = None,
    stage_wrapper: StageWrapper | None = None,
) -> BuildWorkflowResult:
    """
    Esegue la pipeline semantica standard per uno slug.

    - Facoltativamente applica un gating headless (es. `_require_semantic_gating`).
    - Costruisce il contesto cliente tramite `context_factory(slug)`.
    - Delega a `run_semantic_pipeline(context, logger, slug=slug, stage_wrapper=...)`.

    Questa funzione è pensata per CLI, job batch e automazioni, non per la UI:
    la UI può continuare a usare i runner `_run_convert/_run_enrich/_run_summary`
    in `ui.pages.semantics` per avere messaggi e feedback Streamlit.
    """

    safe_slug = slug.strip()
    if not safe_slug:
        raise ConfigError("Slug vuoto non valido per la pipeline semantica.", slug=slug)

    if gating is not None:
        gating(safe_slug)

    ctx = context_factory(safe_slug)
    eff_logger = logger or get_structured_logger("semantic.pipeline", context={"slug": safe_slug})

    return run_semantic_pipeline(
        ctx,
        eff_logger,
        slug=safe_slug,
        stage_wrapper=stage_wrapper,
    )


def build_markdown_book(context: ClientContextType, logger: logging.Logger, *, slug: str) -> list[Path]:
    """Fase unica che copre conversione, summary/readme e arricchimento frontmatter.

    La cache LRU del frontmatter viene sfruttata durante il run e sempre svuotata a fine workflow
    per evitare riuso involontario di stato tra run nella stessa process.
    """
    if logger is None:
        logger = get_structured_logger("semantic.book", context={"slug": slug})
    start_ts = time.perf_counter()
    with phase_scope(logger, stage="build_markdown_book", customer=slug) as m:
        _repo_root_dir, mds, touched = _run_build_workflow(context, logger, slug=slug, stage_wrapper=None)
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
            "enriched_files": len(touched),
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
    chunk_records: Sequence[ChunkRecord] | None = None,
) -> int:
    """Indice i Markdown presenti in book/ nel DB, delegando al servizio dedicato."""
    if getattr(context, "repo_root_dir", None) is None:
        raise ConfigError(
            "Contesto privo di repo_root_dir: impossibile risolvere il workspace in modo deterministico.",
            slug=slug,
        )
    layout = WorkspaceLayout.from_context(cast(Any, context))
    repo_root_dir = layout.repo_root_dir
    book_dir = layout.book_dir
    store = KbStore.for_slug(slug=slug, repo_root_dir=repo_root_dir, db_path=db_path)
    effective_db_path = store.effective_db_path()
    return cast(
        int,
        embedding_service.index_markdown_to_db(
            repo_root_dir=repo_root_dir,
            book_dir=book_dir,
            slug=slug,
            logger=logger,
            scope=scope,
            embeddings_client=embeddings_client,
            db_path=effective_db_path,
            chunk_records=chunk_records,
        ),
    )
