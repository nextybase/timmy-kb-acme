# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility per caricare e validare semantic_mapping.yaml in modo riusabile."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within

__all__ = [
    "MappingLoadResult",
    "load_mapping_file",
    "iter_mapping_candidates",
    "_normalize_semantic_mapping",
    "_has_phase1_keywords",
]


class _YamlReader(Protocol):
    def __call__(self, base_dir: Path, file_path: Path) -> Dict[str, object] | None: ...


@dataclass(frozen=True)
class MappingLoadResult:
    source: str
    path: Path
    mapping: Dict[str, List[str]]


def _normalize_semantic_mapping(raw: Any) -> Dict[str, List[str]]:
    norm: Dict[str, List[str]] = {}
    if not isinstance(raw, dict):
        return norm

    for concept, payload in raw.items():
        kws: List[str] = []
        if isinstance(payload, dict):
            src = None
            if isinstance(payload.get("keywords"), list):
                src = payload.get("keywords")
            elif isinstance(payload.get("tags"), list):
                src = payload.get("tags")
            if src:
                kws = [str(x) for x in src if isinstance(x, (str, int, float))]
        elif isinstance(payload, list):
            kws = [str(x) for x in payload if isinstance(x, (str, int, float))]
        elif isinstance(payload, str):
            kws = [payload]

        kws = [k.strip() for k in kws if str(k).strip()]
        seen = set()
        dedup: List[str] = []
        for k in kws:
            kl = k.lower()
            if kl not in seen:
                seen.add(kl)
                dedup.append(k)
        if dedup:
            norm[str(concept)] = dedup

    return norm


def _has_phase1_keywords(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    for payload in raw.values():
        if isinstance(payload, dict) and "keywords" in payload:
            return True
    return False


def load_mapping_file(
    *,
    base_dir: Path,
    file_path: Path,
    slug: Optional[str],
    yaml_read: _YamlReader,
    source: str,
) -> MappingLoadResult:
    """Carica, valida e normalizza un file di mapping."""
    ensure_within(base_dir, file_path)
    raw = yaml_read(base_dir, file_path) or {}
    if _has_phase1_keywords(raw):
        raise ConfigError(
            "Uso scorretto: 'keywords' non è previsto in semantic_mapping.yaml (Fase 1).",
            slug=slug,
            file_path=str(file_path),
        )
    mapping = _normalize_semantic_mapping(raw)
    return MappingLoadResult(source=source, path=file_path, mapping=mapping)


def iter_mapping_candidates(
    *,
    context_slug: Optional[str],
    config_dir: Optional[Path],
    repo_root_dir: Path,
    repo_default_dir: Optional[Path],
    mapping_filename: str,
) -> Iterable[tuple[str, Path, Path]]:
    """Restituisce una sequenza di candidati (origine, base_dir, file_path)."""
    if config_dir is not None:
        cfg_base = Path(config_dir)
        yield "workspace", cfg_base, cfg_base / mapping_filename

    repo_base = Path(repo_root_dir) / "semantic"
    yield "repo", repo_base, repo_base / mapping_filename

    fallback_root = Path(repo_default_dir or repo_root_dir)
    fallback_base = fallback_root / "config"
    yield "fallback", fallback_base, fallback_base / "default_semantic_mapping.yaml"
