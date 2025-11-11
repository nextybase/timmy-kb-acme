# SPDX-License-Identifier: GPL-3.0-only
"""Utility di ingestion per Timmy KB.

Funzioni:
- ingest_path(project_slug, scope, path, version, meta)
- ingest_folder(project_slug, scope, folder_glob, version, meta)
- get_vision_cfg(cfg)

Legge file di testo, li divide in chunk, calcola le embedding e le salva in SQLite
tramite kb_db.insert_chunks. Salta i file binari. Registra un riepilogo nei log.

Nota Vision: il flusso Vision è ora **inline-only** e delega tutta l’elaborazione
all’Assistant preconfigurato. Non esistono più modalità vector/attachments/fallback.
"""

from __future__ import annotations

from functools import lru_cache
from glob import iglob
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Sequence, cast

from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError, PathTraversalError
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from semantic.types import EmbeddingsClient  # usa la SSoT del protocollo

# IMPORT alias: supporta sia import locale che pacchetto installato
try:
    from src.kb_db import insert_chunks  # type: ignore
except ImportError:
    try:
        from timmykb.kb_db import insert_chunks  # type: ignore
    except ImportError:  # pragma: no cover
        from .kb_db import insert_chunks

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


def _iter_ingest_candidates(
    folder_glob: str,
    base: Path,
    *,
    customer: str | None,
    scope: str,
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
            LOGGER.warning(
                "ingest.skip.traversal",
                extra={
                    "event": "ingest.skip.traversal",
                    "file": str(p),
                    "project": customer,
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
            extra={"event": "ingest.read.unsupported_encoding", "file": str(p)},
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
        resp = self._client.embeddings.create(model=mdl, input=list(texts))
        return [d.embedding for d in resp.data]


def ingest_path(
    project_slug: str,
    scope: str,
    path: str,
    version: str,
    meta: dict[str, Any],
    embeddings_client: Optional[EmbeddingsClient] = None,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """Ingest di un singolo file di testo: chunk, embedding, salvataggio. Restituisce il numero di chunk."""
    p = Path(path)
    if base_dir is None:
        raise ConfigError("Base directory obbligatoria per ingest_path.")
    base = Path(base_dir).resolve()
    if not p.exists() or not p.is_file():
        LOGGER.error(
            "ingest.invalid_file",
            extra={"event": "ingest.invalid_file", "file": str(p)},
        )
        return 0
    try:
        safe_p = ensure_within_and_resolve(base, p)
    except PathTraversalError as exc:
        LOGGER.warning(
            "ingest.skip.traversal",
            extra={
                "event": "ingest.skip.traversal",
                "file": str(p),
                "project": project_slug,
                "scope": scope,
                "error": str(exc),
            },
        )
        return 0
    if _is_binary(safe_p):
        LOGGER.info(
            "ingest.skip.binary",
            extra={"event": "ingest.skip.binary", "file": str(p)},
        )
        return 0
    text = _read_text_file(base, p)
    slug = meta.get("slug") if isinstance(meta, dict) else None
    with phase_scope(LOGGER, stage="ingest.embed", customer=slug) as phase_embed:
        chunks: List[str] = _chunk_text(text)
        phase_embed.set_artifacts(len(chunks))
        client: EmbeddingsClient = embeddings_client or cast(EmbeddingsClient, OpenAIEmbeddings())
        vectors_seq = client.embed_texts(chunks)

        # Converte in List[List[float]] per compatibilità con insert_chunks
        vectors: List[List[float]] = [list(map(float, v)) for v in vectors_seq]
        phase_embed.set_artifacts(len(vectors))

    with phase_scope(LOGGER, stage="ingest.persist", customer=slug) as phase_persist:
        inserted = int(
            insert_chunks(
                project_slug=project_slug,
                scope=scope,
                path=str(safe_p),
                version=version,
                meta_dict=meta,
                chunks=chunks,
                embeddings=vectors,
            )
        )
        phase_persist.set_artifacts(inserted)
    LOGGER.info(
        "ingest.file.saved",
        extra={
            "event": "ingest.file.saved",
            "project": project_slug,
            "scope": scope,
            "file": str(safe_p),
            "chunks": inserted,
        },
    )
    return inserted


def ingest_folder(
    project_slug: str,
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
        project_slug/scope/version/meta: parametri dominio.
        embeddings_client: facoltativo, riuso di un client embedding.
        base_dir: override del perimetro path-safety (default: inferito dal glob).
        max_files: limita il numero massimo di file elaborati (None -> tutti).
        batch_size: numero di file caricati per batch durante lo streaming (None -> 1).

    Restituisce un dizionario di riepilogo con i conteggi: {files, chunks}.
    """
    base = Path(base_dir).resolve() if base_dir is not None else _infer_base_dir(folder_glob)
    client: EmbeddingsClient | None = embeddings_client

    total_chunks = 0
    count_files = 0
    customer = meta.get("slug") if isinstance(meta, dict) else None
    limit_reached = False

    with phase_scope(LOGGER, stage="ingest.discover", customer=customer) as phase_discover:
        discovered = 0

        def _update(count: int) -> None:
            nonlocal discovered
            discovered = count
            phase_discover.set_artifacts(count)

        candidate_iter = _iter_ingest_candidates(
            folder_glob,
            base,
            customer=customer,
            scope=scope,
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
                            project_slug=project_slug,
                            scope=scope,
                            path=str(p),
                            version=version,
                            meta=meta,
                            embeddings_client=client,
                            base_dir=base,
                        )
                        phase_file.set_artifacts(n)
                    if n > 0:
                        total_chunks += n
                        count_files += 1
                except ConfigError as exc:
                    LOGGER.warning(
                        "ingest.skip.config_error",
                        extra={
                            "event": "ingest.skip.config_error",
                            "file": str(p),
                            "scope": scope,
                            "project": project_slug,
                            "error": str(exc),
                        },
                    )
                except Exception:
                    LOGGER.exception(
                        "ingest.error",
                        extra={
                            "event": "ingest.error",
                            "file": str(p),
                            "scope": scope,
                            "project": project_slug,
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
                "event": "ingest.limit_reached",
                "project": project_slug,
                "scope": scope,
                "files_processed": count_files,
                "max_files": max_files,
            },
        )
    with phase_scope(LOGGER, stage="ingest.summary", customer=customer):
        LOGGER.info(
            "ingest.summary",
            extra={
                "event": "ingest.summary",
                "project": project_slug,
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
        "model": None,  # deciso dall'Assistant
        "strict_output": bool(v.get("strict_output", True)),
    }
