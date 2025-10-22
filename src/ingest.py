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

import logging
import os
from glob import glob
from pathlib import Path
from typing import Any, List, Optional, Sequence, cast

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, read_text_safe
from semantic.types import EmbeddingsClient  # usa la SSoT del protocollo

# IMPORT alias: supporta sia import locale che pacchetto installato
try:
    from src.kb_db import insert_chunks  # type: ignore
except ImportError:
    try:
        from timmykb.kb_db import insert_chunks  # type: ignore
    except ImportError:  # pragma: no cover
        from .kb_db import insert_chunks

LOGGER = logging.getLogger("timmy_kb.ingest")


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


def _is_binary(base_dir: Path, path: Path) -> bool:
    try:
        ensure_within(base_dir, path)
        safe_p = cast(Path, ensure_within_and_resolve(base_dir, path))
        with safe_p.open("rb") as f:
            chunk = f.read(1024)
        if b"\0" in chunk:
            return True
        # Euristica: se troppi byte non testuali
        text_bytes = sum(c in b"\n\r\t\f\v\b\x1b" or 32 <= c <= 126 for c in chunk)
        return text_bytes / max(1, len(chunk)) < 0.9
    except Exception:
        return True


def _chunk_text(text: str, target_tokens: int = 400, overlap_tokens: int = 40) -> List[str]:
    """Divide il testo in chunk basati su token quando possibile, altrimenti per caratteri."""
    try:
        import tiktoken
    except Exception as exc:
        raise ConfigError(
            "Il pacchetto 'tiktoken' è richiesto per eseguire l'ingestione. Installa le dipendenze complete."
        ) from exc

    try:
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        raise ConfigError("Impossibile inizializzare l'encoding 'cl100k_base' di tiktoken.") from exc
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
    base = Path(base_dir) if base_dir is not None else p.parent
    if not p.exists() or not p.is_file():
        LOGGER.error(
            "ingest.invalid_file",
            extra={"event": "ingest.invalid_file", "file": str(p)},
        )
        return 0
    if _is_binary(base, p):
        LOGGER.info(
            "ingest.skip.binary",
            extra={"event": "ingest.skip.binary", "file": str(p)},
        )
        return 0
    text = _read_text_file(base, p)
    chunks: List[str] = _chunk_text(text)
    client: EmbeddingsClient = embeddings_client or cast(EmbeddingsClient, OpenAIEmbeddings())
    vectors_seq = client.embed_texts(chunks)

    # Converte in List[List[float]] per compatibilità con insert_chunks
    vectors: List[List[float]] = [list(map(float, v)) for v in vectors_seq]

    inserted = int(
        insert_chunks(
            project_slug=project_slug,
            scope=scope,
            path=str(p),
            version=version,
            meta_dict=meta,
            chunks=chunks,
            embeddings=vectors,
        )
    )
    LOGGER.info(
        "ingest.file.saved",
        extra={
            "event": "ingest.file.saved",
            "project": project_slug,
            "scope": scope,
            "file": str(p),
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
) -> dict[str, int]:
    """Ingest di tutti i file .md/.txt che corrispondono al glob indicato.

    Restituisce un dizionario di riepilogo con i conteggi: {files, chunks}.
    """
    files = [Path(p) for p in glob(folder_glob, recursive=True)]
    files = [p for p in files if p.is_file() and p.suffix.lower() in {".md", ".txt"}]
    # Short-circuit su input vuoto
    if not files:
        LOGGER.info(
            "ingest.summary",
            extra={
                "event": "ingest.summary",
                "project": project_slug,
                "scope": scope,
                "files": 0,
                "chunks": 0,
            },
        )
        return {"files": 0, "chunks": 0}

    # Riuso di un singolo client embeddings quando non fornito
    client: EmbeddingsClient | None = embeddings_client or cast(EmbeddingsClient, OpenAIEmbeddings())

    total_chunks = 0
    count_files = 0
    for p in files:
        try:
            n = ingest_path(
                project_slug=project_slug,
                scope=scope,
                path=str(p),
                version=version,
                meta=meta,
                embeddings_client=client,
                base_dir=p.parent,
            )
            if n > 0:
                total_chunks += n
                count_files += 1
        except Exception as e:  # ingest robusto
            LOGGER.exception(
                "ingest.error",
                extra={
                    "event": "ingest.error",
                    "file": str(p),
                    "scope": scope,
                    "project": project_slug,
                    "error": str(e),
                },
            )
            continue
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
    assistant_id = (os.getenv("OBNEXT_ASSISTANT_ID") or os.getenv("ASSISTANT_ID") or "").strip()
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
