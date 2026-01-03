# SPDX-License-Identifier: GPL-3.0-only
"""Utility di ingestion per Timmy KB.

Funzioni:
- ingest_path(slug, scope, path, version, meta)
- ingest_folder(slug, scope, folder_glob, version, meta)
- get_vision_cfg(cfg)

Legge file di testo, li divide in chunk, calcola le embedding e le salva in SQLite
tramite kb_db.insert_chunks. Salta i file binari. Registra un riepilogo nei log.

Nota Vision: il flusso Vision è ora **inline-only** e delega tutta l’elaborazione
all’Assistant preconfigurato. Non esistono più modalità vector/attachments/fallback.
"""

from __future__ import annotations

import hashlib
import os
import time
from functools import lru_cache
from glob import iglob
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Sequence, cast

# Importa kb_db in modo locale senza alias legacy
from kb_db import insert_chunks
from pipeline.context import ClientContext
from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError, PathTraversalError
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.metrics import record_document_processed, start_metrics_server_once
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.tracing import start_decision_span, start_root_trace
from semantic.types import EmbeddingsClient  # usa la SSoT del protocollo
from storage.kb_store import KbStore

LOGGER = get_structured_logger("timmy_kb.ingest")

_WILDCARD_CHARS = ("*", "?", "[")


def _infer_base_dir(folder_glob: str | Path) -> Path:
    """Ricava una directory base dal glob (prima dei wildcard)."""
    pattern = str(folder_glob)
    first_wildcard = len(pattern)
    for char in _WILDCARD_CHARS:
        idx = pattern.find(char)
        if idx != -1:
            first_wildcard = min(first_wildcard, idx)
    prefix = pattern[:first_wildcard]
    if not prefix:
        return Path(".").resolve()
    sep_idx = max(prefix.rfind("/"), prefix.rfind("\\"))
    base_slice = prefix if sep_idx == -1 else prefix[: sep_idx + 1]
    base_candidate = Path(base_slice or ".")
    return base_candidate.resolve()


def _relative_to(base: Path, candidate: Path) -> str:
    try:
        return str(candidate.relative_to(base))
    except Exception:
        return str(candidate)


def _resolve_workspace_base(slug: str) -> Optional[Path]:
    """
    Best-effort resolution del workspace per uno slug.

    Priorità:
    1) ClientContext.load(...).base_dir
    2) Se raw_dir è presente, usa raw_dir.parent
    3) semantic.api.get_paths(slug)["base"]
    4) Fallback None (DB globale)
    """
    slug = (slug or "").strip()
    if not slug:
        return None
    try:
        ctx = ClientContext.load(slug=slug, require_env=False, run_id=None)
        base_dir = getattr(ctx, "base_dir", None)
        if isinstance(base_dir, Path):
            return base_dir
        raw_dir = getattr(ctx, "raw_dir", None)
        if isinstance(raw_dir, Path):
            return raw_dir.parent
    except Exception:
        pass

    try:
        from semantic.api import get_paths as _get_paths

        paths = _get_paths(slug)
        base = paths.get("base")
        if isinstance(base, Path):
            return base
        if base is not None:
            return Path(str(base))
    except Exception:
        return None

    return None


def _build_lineage(
    *,
    slug: str,
    scope: str,
    version: str,
    base_dir: Path,
    safe_path: Path,
    chunks: Sequence[str],
) -> dict[str, Any]:
    relative_path = _relative_to(base_dir, safe_path)
    source_id = f"{slug}:{scope}:{version}:{relative_path}"
    lineage_chunks = []
    for idx, _chunk in enumerate(chunks):
        chunk_hash = hashlib.sha256(f"{source_id}:{idx}".encode("utf-8")).hexdigest()
        lineage_chunks.append(
            {
                "chunk_index": idx,
                "chunk_id": chunk_hash,
                "embedding_id": chunk_hash,
            }
        )
    return {"source_id": source_id, "chunks": lineage_chunks}


def discover_files(
    folder_glob: str,
    base_dir: Path,
    *,
    slug: str,
    scope: str,
    customer: str | None,
    on_count: Callable[[int], None] | None = None,
) -> Iterable[Path]:
    """Wrapper pubblico per `_iter_ingest_candidates`."""
    return _iter_ingest_candidates(
        folder_glob,
        base_dir,
        customer=customer,
        scope=scope,
        slug=slug,
        on_count=on_count,
    )


def _iter_ingest_candidates(
    folder_glob: str,
    base: Path,
    *,
    customer: str | None,
    scope: str,
    slug: str,
    on_count: Callable[[int], None] | None = None,
) -> Iterable[Path]:
    allowed_suffixes = {".md", ".txt"}
    produced = 0
    for raw in iglob(folder_glob, recursive=True):
        p = Path(raw)
        if not p.is_file():
            continue
        if p.suffix.lower() not in allowed_suffixes:
            continue
        try:
            safe = ensure_within_and_resolve(base, p)
        except PathTraversalError as exc:
            with start_decision_span(
                "filter",
                slug=customer or slug,
                run_id=None,
                trace_kind="ingest",
                phase="ingest.discover",
                attributes={
                    "decision_type": "filter",
                    "file_path_relative": _relative_to(base, p),
                    "reason": "traversal",
                    "status": "blocked",
                    "error": str(exc),
                },
            ):
                LOGGER.warning(
                    "ingest.skip.traversal",
                    extra={
                        "file": str(p),
                        "slug": customer,
                        "scope": scope,
                        "error": str(exc),
                    },
                )
            continue
        produced += 1
        if on_count is not None:
            on_count(produced)
        yield safe


def _batched_iterable(items: Iterable[Path], batch_size: int | None) -> Iterable[list[Path]]:
    if batch_size is None or batch_size <= 0:
        for item in items:
            yield [item]
        return
    batch: list[Path] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _read_text_file(base_dir: Path, p: Path) -> str:
    try:
        # Prova prima con UTF-8
        return cast(str, read_text_safe(base_dir, p, encoding="utf-8"))
    except UnicodeDecodeError as exc:
        LOGGER.error(
            "ingest.read.unsupported_encoding",
            extra={"file": str(p)},
        )
        raise ConfigError(
            f"Il file {p} non è codificato in UTF-8. Converti il file in UTF-8 prima di procedere."
        ) from exc


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(1024)
    except Exception:
        return True
    if b"\0" in chunk:
        return True
    text_bytes = sum(c in b"\n\r\t\f\v\b\x1b" or 32 <= c <= 126 for c in chunk)
    return text_bytes / max(1, len(chunk)) < 0.9


def load_and_chunk(
    *,
    path: Path,
    base_dir: Path,
    slug: str,
    scope: str,
    customer: str | None,
) -> tuple[Optional[Path], list[str]]:
    """Applica path-safety, filtro binario e chunking. Restituisce (safe_path, chunks)."""
    base = Path(base_dir).resolve()
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        LOGGER.error(
            "ingest.invalid_file",
            extra={"file": str(candidate), "slug": slug},
        )
        return None, []
    try:
        safe_path = ensure_within_and_resolve(base, candidate)
    except PathTraversalError as exc:
        with start_decision_span(
            "filter",
            slug=customer or slug,
            run_id=None,
            trace_kind="ingest",
            phase="ingest.process_file",
            attributes={
                "decision_type": "filter",
                "file_path_relative": _relative_to(base, candidate),
                "reason": "traversal",
                "status": "blocked",
                "error": str(exc),
            },
        ):
            LOGGER.warning(
                "ingest.skip.traversal",
                extra={
                    "file": str(candidate),
                    "slug": slug,
                    "scope": scope,
                    "error": str(exc),
                },
            )
        return None, []

    if _is_binary(safe_path):
        with start_decision_span(
            "filter",
            slug=customer or slug,
            run_id=None,
            trace_kind="ingest",
            phase="ingest.process_file",
            attributes={
                "decision_type": "filter",
                "file_path_relative": _relative_to(base, candidate),
                "reason": "binary",
                "status": "blocked",
            },
        ):
            LOGGER.info(
                "ingest.skip.binary",
                extra={"file": str(candidate), "slug": slug},
            )
        return None, []

    text = _read_text_file(base, candidate)
    chunks: list[str] = _chunk_text(text)
    return safe_path, chunks


def embed_and_persist(
    *,
    slug: str,
    scope: str,
    version: str,
    safe_path: Path,
    chunks: list[str],
    meta: dict[str, Any],
    base_dir: Path,
    embeddings_client: EmbeddingsClient | None,
    db_path: Path,
    customer: str | None,
) -> int:
    """Calcola le embedding e persiste i chunk nel DB, restituendo il totale inserito."""
    client: EmbeddingsClient = embeddings_client or cast(EmbeddingsClient, OpenAIEmbeddings())
    safe_rel_path = _relative_to(base_dir, safe_path)
    meta_dict = dict(meta or {})
    lineage_meta = meta_dict.get("lineage")
    if not isinstance(lineage_meta, dict):
        lineage_meta = _build_lineage(
            slug=slug,
            scope=scope,
            version=version,
            base_dir=base_dir,
            safe_path=safe_path,
            chunks=chunks,
        )
        meta_dict.setdefault("lineage", lineage_meta)
    LOGGER.info(
        "semantic.input.received",
        extra={
            "slug": slug,
            "scope": scope,
            "source_id": lineage_meta.get("source_id"),
            "source_path": safe_rel_path,
            "ingestion_run_id": meta_dict.get("run_id"),
        },
    )
    for chunk in lineage_meta.get("chunks", []):
        LOGGER.info(
            "semantic.lineage.chunk_created",
            extra={
                "slug": slug,
                "scope": scope,
                "path": safe_rel_path,
                "source_id": lineage_meta.get("source_id"),
                "chunk_id": chunk.get("chunk_id"),
                "chunk_index": chunk.get("chunk_index"),
            },
        )
    with phase_scope(LOGGER, stage="ingest.embed", customer=customer or slug) as phase_embed:
        vectors_seq = client.embed_texts(chunks)
        vectors: list[list[float]] = [list(map(float, v)) for v in vectors_seq]
        phase_embed.set_artifacts(len(vectors))

    with phase_scope(LOGGER, stage="ingest.persist", customer=customer or slug) as phase_persist:
        inserted = int(
            insert_chunks(
                slug=slug,
                scope=scope,
                path=str(safe_path),
                version=version,
                meta_dict=meta_dict,
                chunks=chunks,
                embeddings=vectors,
                db_path=db_path,
            )
        )
        phase_persist.set_artifacts(inserted)

    LOGGER.info(
        "ingest.file.saved",
        extra={
            "slug": slug,
            "scope": scope,
            "file": str(safe_path),
            "chunks": inserted,
            "source_id": lineage_meta.get("source_id"),
        },
    )
    LOGGER.info(
        "semantic.lineage.embedding_registered",
        extra={
            "slug": slug,
            "scope": scope,
            "path": safe_rel_path,
            "source_id": lineage_meta.get("source_id"),
            "version": version,
            "embedding_count": len(chunks),
        },
    )
    if inserted > 0:
        try:
            record_document_processed(slug, inserted)
        except Exception:
            pass
    return inserted


@lru_cache(maxsize=1)
def _get_encoder() -> Any:
    try:
        import tiktoken
    except Exception as exc:
        raise ConfigError(
            "Il pacchetto 'tiktoken' è richiesto per eseguire l'ingestione. Installa le dipendenze complete."
        ) from exc

    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        raise ConfigError("Impossibile inizializzare l'encoding 'cl100k_base' di tiktoken.") from exc


def _chunk_text(text: str, target_tokens: int = 400, overlap_tokens: int = 40) -> List[str]:
    """Divide il testo in chunk basati su token quando possibile, altrimenti per caratteri."""
    enc = _get_encoder()
    tokens = enc.encode(text)
    chunks = []
    step = max(1, target_tokens - overlap_tokens)
    for i in range(0, len(tokens), step):
        piece = tokens[i : i + target_tokens]
        chunks.append(enc.decode(piece))
    return chunks


class OpenAIEmbeddings:
    """Client semplice per calcolare embedding tramite API openai>=1.x."""

    def __init__(
        self: "OpenAIEmbeddings",
        model: str = "text-embedding-3-small",
        *,
        api_key: str | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except Exception as e:  # pragma: no cover - errore di import
            raise RuntimeError("Pacchetto openai non disponibile. Installa openai>=1.x") from e
        self._OpenAI = OpenAI
        # Iniezione opzionale della chiave senza mutare l'ambiente
        self._client = OpenAI(api_key=api_key) if api_key else OpenAI()
        self._model = model

    def embed_texts(
        self: "OpenAIEmbeddings",
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> Sequence[Sequence[float]]:
        # Uniformiamo a Sequence[str] e supportiamo il parametro keyword-only `model`
        if not texts:
            return cast(Sequence[Sequence[float]], [])
        mdl = model or self._model
        t0 = time.perf_counter()
        resp = self._client.embeddings.create(model=mdl, input=list(texts))
        latency_ms = (time.perf_counter() - t0) * 1000.0
        LOGGER.info(
            "openai.api_calls",
            extra={
                "model": mdl,
                "count": len(texts),
                "latency_ms": float(latency_ms),
            },
        )
        return [d.embedding for d in resp.data]


def ingest_path(
    slug: str,
    scope: str,
    path: str,
    version: str,
    meta: dict[str, Any],
    embeddings_client: Optional[EmbeddingsClient] = None,
    *,
    base_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> int:
    """Ingest di un singolo file di testo: chunk, embedding, salvataggio. Restituisce il numero di chunk.

    Funzione di orchestrazione: delega path-safety/lettura a load_and_chunk e l'embed/persist a embed_and_persist.
    """
    effective_db_path = db_path
    if effective_db_path is None:
        # Riusabile stand-alone: se ingest_folder non ha già risolto il DB, calcola qui il workspace.
        workspace_base = _resolve_workspace_base(slug)
        store = KbStore.for_slug(slug, base_dir=workspace_base)
        effective_db_path = store.effective_db_path()
    p = Path(path)
    if base_dir is None:
        raise ConfigError("Base directory obbligatoria per ingest_path.")
    base = Path(base_dir).resolve()
    customer = meta.get("slug") if isinstance(meta, dict) else None
    safe_path, chunks = load_and_chunk(
        path=p,
        base_dir=base,
        slug=slug,
        scope=scope,
        customer=customer,
    )
    if not chunks or safe_path is None:
        return 0
    return embed_and_persist(
        slug=slug,
        scope=scope,
        version=version,
        safe_path=safe_path,
        chunks=chunks,
        meta=meta,
        base_dir=base,
        embeddings_client=embeddings_client,
        db_path=effective_db_path,
        customer=customer,
    )


def ingest_folder(
    slug: str,
    scope: str,
    folder_glob: str,
    version: str,
    meta: dict[str, Any],
    embeddings_client: Optional[EmbeddingsClient] = None,
    *,
    base_dir: Optional[Path] = None,
    max_files: Optional[int] = None,
    batch_size: Optional[int] = None,
) -> dict[str, int]:
    """Ingest di tutti i file .md/.txt che corrispondono al glob indicato.

    Args:
        slug/scope/version/meta: parametri dominio.
        embeddings_client: facoltativo, riuso di un client embedding.
        base_dir: override del perimetro path-safety (default: inferito dal glob).
        max_files: limita il numero massimo di file elaborati (None -> tutti).
        batch_size: numero di file caricati per batch durante lo streaming (None -> 1).

    Restituisce un dizionario di riepilogo con i conteggi: {files, chunks}.
    """
    start_metrics_server_once()
    base = Path(base_dir).resolve() if base_dir is not None else _infer_base_dir(folder_glob)
    client: EmbeddingsClient | None = embeddings_client
    workspace_base = _resolve_workspace_base(slug)
    store = KbStore.for_slug(slug, base_dir=workspace_base)
    db_path = store.effective_db_path()
    if slug:
        LOGGER.info("ingest.db_path", extra={"slug": slug, "db_path": str(db_path)})

    total_chunks = 0
    count_files = 0
    customer = meta.get("slug") if isinstance(meta, dict) else None
    limit_reached = False
    env = os.getenv("TIMMY_ENV", "dev")
    root_slug = customer or slug
    run_id = meta.get("run_id") if isinstance(meta, dict) else None

    with start_root_trace(
        "ingest",
        slug=root_slug,
        run_id=run_id,
        entry_point="cli",
        env=env,
        trace_kind="ingest",
    ):
        with phase_scope(LOGGER, stage="ingest.discover", customer=customer) as phase_discover:
            discovered = 0

            def _update(count: int) -> None:
                nonlocal discovered
                discovered = count
                phase_discover.set_artifacts(count)

            candidate_iter = discover_files(
                folder_glob,
                base,
                slug=slug,
                scope=scope,
                customer=customer,
                on_count=_update,
            )
            for batch in _batched_iterable(candidate_iter, batch_size):
                for p in batch:
                    if max_files is not None and max_files >= 0 and count_files >= max_files:
                        limit_reached = True
                        break
                    try:
                        with phase_scope(LOGGER, stage="ingest.process_file", customer=customer) as phase_file:
                            if client is None:
                                client = cast(EmbeddingsClient, OpenAIEmbeddings())
                            n = ingest_path(
                                slug=slug,
                                scope=scope,
                                path=str(p),
                                version=version,
                                meta=meta,
                                embeddings_client=client,
                                base_dir=base,
                                db_path=db_path,
                            )
                            phase_file.set_artifacts(n)
                        if n > 0:
                            total_chunks += n
                            count_files += 1
                            if count_files % 50 == 0:
                                LOGGER.info(
                                    "pipeline.processing.progress",
                                    extra={
                                        "slug": slug,
                                        "scope": scope,
                                        "processed": count_files,
                                        "chunks": total_chunks,
                                    },
                                )
                    except ConfigError as exc:
                        LOGGER.warning(
                            "ingest.skip.config_error",
                            extra={
                                "file": str(p),
                                "scope": scope,
                                "slug": slug,
                                "error": str(exc),
                            },
                        )
                    except Exception:
                        LOGGER.exception(
                            "ingest.error",
                            extra={
                                "file": str(p),
                                "scope": scope,
                                "slug": slug,
                            },
                        )
                        raise
                if limit_reached:
                    break
            if discovered == 0 and count_files == 0 and not limit_reached:
                phase_discover.set_artifacts(0)

    if limit_reached:
        LOGGER.info(
            "ingest.limit_reached",
            extra={
                "slug": slug,
                "scope": scope,
                "files_processed": count_files,
                "max_files": max_files,
            },
        )
    with phase_scope(LOGGER, stage="ingest.summary", customer=customer):
        LOGGER.info(
            "ingest.summary",
            extra={
                "slug": slug,
                "scope": scope,
                "files": count_files,
                "chunks": total_chunks,
            },
        )
    return {"files": count_files, "chunks": total_chunks}


# --- Vision config (inline-only, assistant) ---
def get_vision_cfg(cfg: dict | None) -> dict:
    """
    Restituisce la configurazione Vision normalizzata **inline-only**.
    - Percorso unico: engine = "assistant" (Threads/Runs), niente vector/attachments/fallback.
    - Modello non configurato qui: lo decide il profilo Assistant (dashboard).
    - `assistant_id` è OBBLIGATORIO: letto da OBNEXT_ASSISTANT_ID o ASSISTANT_ID.
    - `strict_output` resta abilitato di default.
    """
    v = (cfg or {}).get("vision") or {}
    assistant_id = (get_env_var("OBNEXT_ASSISTANT_ID", default=None) or get_env_var("ASSISTANT_ID", default="")).strip()
    if not assistant_id:
        raise ConfigError("Assistant ID non configurato: imposta OBNEXT_ASSISTANT_ID o ASSISTANT_ID.")

    return {
        "engine": "assistant",
        "assistant_id": assistant_id,
        "input_mode": "inline",  # documentativo
        "fs_mode": None,  # rimosso
        "model": None,  # deciso da l'Assistant
        "strict_output": bool(v.get("strict_output", True)),
    }
