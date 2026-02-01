# SPDX-License-Identifier: GPL-3.0-or-later
"""Skeleton ExplainabilityService per costruire l'Explainability Packet.

Questa versione non interroga DB o log: normalizza il manifest di risposta,
estrae le evidenze (rank/score/lineage) e prepara placeholder per arricchimenti
successivi.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, Literal, Mapping, MutableMapping, Sequence

from explainability.manifest import ResponseManifest
from storage.kb_db import fetch_candidates


class ExplainabilityService:
    """Costruisce un Explainability Packet a partire dal manifest per-risposta."""

    @contextmanager
    def capture_logs(self, level: int = logging.INFO) -> Iterator[list[logging.LogRecord]]:
        """Context manager che cattura eventi semantic.* e retriever.*.

        Uso consigliato: con questo context si esegue la fase di search, poi
        `build_response_packet(..., log_records=records)`.
        """
        logger = logging.getLogger()
        records: list[logging.LogRecord] = []

        class _Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                if record.name.startswith("semantic") or record.name.startswith("timmy_kb.retriever"):
                    records.append(record)

        handler = _Collector(level=level)
        logger.addHandler(handler)
        try:
            yield records
        finally:
            logger.removeHandler(handler)

    def build_response_packet(
        self,
        slug: str,
        response_id: str,
        manifest: ResponseManifest,
        detail: Literal["standard", "full"] = "standard",
        *,
        db_path: str | None = None,
        log_records: Iterable[logging.LogRecord] | None = None,
        max_candidates: int = 5000,
    ) -> Dict[str, Any]:
        """Assembla il packet senza I/O né accessi a DB/log.

        Args:
            slug: workspace/cliente di riferimento.
            response_id: identificatore della risposta (cross-log).
            manifest: manifest per-risposta già costruito (vedi manifest.py).
            detail: livello di dettaglio richiesto; per ora standard/full equivalenti.
            db_path: opzionale, path del DB SQLite da cui leggere i meta (read-only).
            log_records: opzionale, lista di LogRecord già catturati (es. via capture_logs).
            max_candidates: limite di fetch per la risoluzione lineage.
        """
        if not manifest:
            raise ValueError("manifest mancante")
        if manifest.get("response_id") != response_id:
            raise ValueError("response_id non coerente con manifest")

        evidence_list: Sequence[Mapping[str, Any]] = manifest.get("evidence", []) or []
        lineage_lookup = self._load_lineage_entries(
            slug=slug,
            scope=str(manifest.get("scope") or ""),
            evidence=evidence_list,
            db_path=db_path,
            max_candidates=max_candidates,
        )
        normalized_evidence = []
        normalized_lineage = []
        for item in evidence_list:
            rank = item.get("rank")
            score = item.get("score")
            source_id = item.get("source_id")
            chunk_id = item.get("chunk_id")
            path = item.get("path")
            normalized_evidence.append(
                {
                    "rank": int(rank) if rank is not None else None,
                    "score": float(score) if score is not None else None,
                    "source_id": source_id,
                    "chunk_id": chunk_id,
                }
            )
            lineage_entry = lineage_lookup.get(chunk_id or source_id) if lineage_lookup else None
            normalized_lineage.append(
                {
                    "source_id": source_id,
                    "chunk_id": chunk_id,
                    "path": lineage_entry.get("path") if lineage_entry else path,
                    "version": lineage_entry.get("version") if lineage_entry else None,
                    "chunk_index": lineage_entry.get("chunk_index") if lineage_entry else None,
                    "status": lineage_entry.get("status") if lineage_entry else "unresolved",
                }
            )

        logs_ref = self._normalize_logs(
            log_records or [],
            evidence_list=evidence_list,
            response_id=response_id,
            detail=detail,
        )

        packet: Dict[str, Any] = {
            "response": {
                "response_id": response_id,
                "timestamp": manifest.get("timestamp"),
            },
            "question": {
                "slug": slug,
                "scope": manifest.get("scope"),
                "query": manifest.get("query"),
                "params": manifest.get("retriever_params") or {},
            },
            "retrieval": {
                "metrics": manifest.get("metrics") or {},
                "model": manifest.get("model") or {},
                "detail": detail,
            },
            "evidence": normalized_evidence,
            "lineage": normalized_lineage,
            "logs_ref": logs_ref,
        }
        return packet

    def _load_lineage_entries(
        self,
        *,
        slug: str,
        scope: str,
        evidence: Sequence[Mapping[str, Any]],
        db_path: str | None,
        max_candidates: int,
    ) -> Dict[str | None, Dict[str, Any]]:
        """Carica i meta dal DB per risolvere path/version/chunk_index."""
        targets = {item.get("chunk_id") for item in evidence if item.get("chunk_id")}
        if not targets:
            return {}
        resolved: Dict[str | None, Dict[str, Any]] = {}
        try:
            candidates = list(fetch_candidates(slug, scope, limit=max_candidates, db_path=db_path))
        except Exception:
            return {}
        for cand in candidates:
            meta = cand.get("meta") if isinstance(cand, Mapping) else {}
            if not isinstance(meta, Mapping):
                continue
            lineage = meta.get("lineage")
            if not isinstance(lineage, Mapping):
                continue
            chunks = lineage.get("chunks")
            if not isinstance(chunks, Sequence):
                continue
            for idx, chunk in enumerate(chunks):
                if not isinstance(chunk, Mapping):
                    continue
                chunk_id = chunk.get("chunk_id")
                if chunk_id not in targets:
                    continue
                resolved[chunk_id] = {
                    "path": chunk.get("path") or meta.get("path"),
                    "version": lineage.get("version") or meta.get("version"),
                    "chunk_index": chunk.get("chunk_index", idx),
                    "status": "resolved",
                }
        return resolved

    def _normalize_logs(
        self,
        records: Iterable[logging.LogRecord],
        *,
        evidence_list: Sequence[Mapping[str, Any]],
        response_id: str,
        detail: Literal["standard", "full"],
    ) -> Dict[str, Any]:
        """Filtra i LogRecord per eventi semantic.* e retriever.* legati alla risposta."""
        evidence_chunk_ids = {item.get("chunk_id") for item in evidence_list if item.get("chunk_id")}
        evidence_source_ids = {item.get("source_id") for item in evidence_list if item.get("source_id")}

        semantic_events: list[Any] = []
        retriever_events: list[Any] = []

        for rec in records:
            name = getattr(rec, "name", "")
            msg = rec.getMessage()
            extra_resp = getattr(rec, "response_id", None)
            src_id = getattr(rec, "source_id", None)
            chk_id = getattr(rec, "chunk_id", None)
            if extra_resp and extra_resp != response_id:
                continue
            if src_id and evidence_source_ids and src_id not in evidence_source_ids:
                continue
            if chk_id and evidence_chunk_ids and chk_id not in evidence_chunk_ids:
                continue
            payload: MutableMapping[str, Any] = {
                "event": msg,
                "timestamp": getattr(rec, "asctime", None),
            }
            if detail == "full":
                payload["extra"] = {
                    k: getattr(rec, k)
                    for k in ("response_id", "source_id", "chunk_id", "slug", "scope")
                    if hasattr(rec, k)
                }
            if name.startswith("timmy_kb.retriever"):
                retriever_events.append(payload)
            elif name.startswith("semantic"):
                semantic_events.append(payload)

        return {"semantic": semantic_events, "retriever": retriever_events}


__all__ = ["ExplainabilityService"]
