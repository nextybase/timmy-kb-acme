"""Ingestion utilities for Timmy KB.

Functions:
- ingest_path(project_slug, scope, path, version, meta)
- ingest_folder(project_slug, scope, folder_glob, version, meta)

Reads text files, splits into chunks, embeds, and stores in SQLite via
kb_db.insert_chunks. Skips binary files. Logs a summary.
"""

from __future__ import annotations

import logging
from glob import glob
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Sequence

from semantic.types import EmbeddingsClient  # usa la SSoT del protocollo
from .kb_db import insert_chunks

LOGGER = logging.getLogger("timmy_kb.ingest")


def _read_text_file(p: Path) -> Optional[str]:
    try:
        # Try UTF-8 first
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Fallback common encodings (senza continue in except)
        for enc in ("utf-16", "latin-1"):
            try:
                return p.read_text(encoding=enc)
            except (UnicodeDecodeError, OSError):
                LOGGER.debug("Fallback encoding failed for %s with %s", p, enc)
        LOGGER.warning("Cannot read text file: %s", p)
        return None


def _is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
        if b"\0" in chunk:
            return True
        # Heuristic: if many non-text bytes
        text_bytes = sum(c in b"\n\r\t\f\v\b\x1b" or 32 <= c <= 126 for c in chunk)
        return text_bytes / max(1, len(chunk)) < 0.9
    except Exception:
        return True


def _try_import_tiktoken() -> ModuleType | None:
    try:
        import tiktoken  # type: ignore

        return tiktoken
    except Exception:
        return None


def _chunk_text(text: str, target_tokens: int = 400, overlap_tokens: int = 40) -> List[str]:
    """Chunk text by tokens when possible, else by chars."""
    tk = _try_import_tiktoken()
    if tk is None:
        # Fallback: char length ~ 4 chars per token heuristic
        size = target_tokens * 4
        ov = overlap_tokens * 4
        chunks: List[str] = []
        i = 0
        while i < len(text):
            chunks.append(text[i : i + size])
            i += max(1, size - ov)
        return chunks

    enc = tk.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    step = max(1, target_tokens - overlap_tokens)
    for i in range(0, len(tokens), step):
        piece = tokens[i : i + target_tokens]
        chunks.append(enc.decode(piece))
    return chunks


class OpenAIEmbeddings(EmbeddingsClient):
    """Simple embeddings client around openai>=1.x API."""

    def __init__(self: "OpenAIEmbeddings", model: str = "text-embedding-3-small") -> None:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover - import error path
            raise RuntimeError("openai package not available. Please install openai>=1.x") from e
        self._OpenAI = OpenAI
        self._client = OpenAI()
        self._model = model

    def embed_texts(
        self: "OpenAIEmbeddings",
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> Sequence[Sequence[float]]:
        # Uniformiamo a Sequence[str] e supportiamo il parametro keyword-only `model`
        if not texts:
            return []
        mdl = model or self._model
        resp = self._client.embeddings.create(model=mdl, input=list(texts))
        return [d.embedding for d in resp.data]


def ingest_path(
    project_slug: str,
    scope: str,
    path: str,
    version: str,
    meta: Dict,
    embeddings_client: Optional[EmbeddingsClient] = None,
) -> int:
    """Ingest a single text file: chunk, embed, save. Returns chunk count."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        LOGGER.error("ingest_path: not a file: %s", path)
        return 0
    if _is_binary(p):
        LOGGER.info("Skipping binary file: %s", path)
        return 0
    text = _read_text_file(p)
    if text is None:
        return 0
    chunks: List[str] = _chunk_text(text)
    client = embeddings_client or OpenAIEmbeddings()
    vectors_seq = client.embed_texts(chunks)

    # Converte in List[List[float]] per compat con insert_chunks
    vectors: List[List[float]] = [list(map(float, v)) for v in vectors_seq]

    inserted = insert_chunks(
        project_slug=project_slug,
        scope=scope,
        path=str(p),
        version=version,
        meta_dict=meta,
        chunks=chunks,
        embeddings=vectors,
    )
    LOGGER.info(
        "ingest_path: %s -> %d chunks stored for %s/%s", path, inserted, project_slug, scope
    )
    return inserted


def ingest_folder(
    project_slug: str,
    scope: str,
    folder_glob: str,
    version: str,
    meta: Dict,
    embeddings_client: Optional[EmbeddingsClient] = None,
) -> Dict[str, int]:
    """Ingest all .md/.txt files under the given glob.

    Returns a summary dict with counts: {files, chunks}.
    """
    files = [Path(p) for p in glob(folder_glob, recursive=True)]
    files = [p for p in files if p.is_file() and p.suffix.lower() in {".md", ".txt"}]
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
                embeddings_client=embeddings_client,
            )
            if n > 0:
                total_chunks += n
                count_files += 1
        except Exception as e:  # robust ingest
            LOGGER.exception("Error ingesting %s: %s", p, e)
            continue
    LOGGER.info(
        "ingest_folder summary: files=%d chunks=%d scope=%s project=%s",
        count_files,
        total_chunks,
        scope,
        project_slug,
    )
    return {"files": count_files, "chunks": total_chunks}
