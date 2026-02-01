# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers per l'indice normalized (INDEX.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

ALLOWED_STATUSES = {"OK", "SKIP", "FAIL"}


@dataclass(frozen=True)
class NormalizedIndexRecord:
    source_path: str
    normalized_path: str | None
    status: str
    input_hash: str | None
    output_hash: str | None
    transformer_name: str
    transformer_version: str
    ruleset_hash: str
    error: str | None = None


def write_index(index_path: Path, records: Iterable[NormalizedIndexRecord]) -> None:
    payload = [record.__dict__ for record in records]
    safe_write_text(
        index_path, json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8", atomic=True
    )


def load_index(repo_root_dir: Path, index_path: Path) -> list[dict[str, object]]:
    safe_index = ensure_within_and_resolve(repo_root_dir, index_path)
    if not safe_index.exists():
        raise ConfigError("normalized/INDEX.json mancante.", file_path=str(safe_index))
    raw = read_text_safe(safe_index.parent, safe_index, encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError("normalized/INDEX.json non valido (JSON).", file_path=str(safe_index)) from exc
    if not isinstance(data, list):
        raise ConfigError("normalized/INDEX.json deve essere una lista.", file_path=str(safe_index))
    return data


def validate_index(
    *,
    repo_root_dir: Path,
    normalized_dir: Path,
    index_path: Path,
) -> list[dict[str, object]]:
    records = load_index(repo_root_dir, index_path)
    seen_outputs: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            raise ConfigError("normalized/INDEX.json contiene record non validi.", file_path=str(index_path))
        status = str(item.get("status") or "")
        if status not in ALLOWED_STATUSES:
            raise ConfigError(
                f"normalized/INDEX.json status non valido: {status}",
                file_path=str(index_path),
            )
        normalized_path = item.get("normalized_path")
        if status == "OK":
            if not isinstance(normalized_path, str) or not normalized_path.strip():
                raise ConfigError("normalized/INDEX.json record OK senza normalized_path.", file_path=str(index_path))
            rel = normalized_path.strip()
            if rel in seen_outputs:
                raise ConfigError(
                    f"normalized/INDEX.json duplicato: {rel}",
                    file_path=str(index_path),
                )
            seen_outputs.add(rel)
            candidate = ensure_within_and_resolve(normalized_dir, normalized_dir / rel)
            if not candidate.exists():
                raise ConfigError(
                    f"normalized/INDEX.json punta a file mancante: {rel}",
                    file_path=str(candidate),
                )
    return records


__all__ = [
    "ALLOWED_STATUSES",
    "NormalizedIndexRecord",
    "write_index",
    "load_index",
    "validate_index",
]
