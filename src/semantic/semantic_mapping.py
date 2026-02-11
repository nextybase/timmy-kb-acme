# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/semantic_mapping.py
"""Gestione del mapping semantico (fase di arricchimento)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Protocol, cast

from pipeline.constants import SEMANTIC_MAPPING_FILE
from pipeline.exceptions import ConfigError, PipelineError
from pipeline.logging_utils import get_structured_logger
from semantic.mapping_loader import iter_mapping_candidates, load_mapping_file

__all__ = ["load_semantic_mapping"]


class _Ctx(Protocol):
    config_dir: Optional[Path]
    repo_root_dir: Optional[Path]
    slug: Optional[str]


def _require_slug(context: _Ctx) -> str:
    try:
        slug_value = context.slug
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise ConfigError("Contesto incompleto: slug mancante", slug=None) from exc
    if not slug_value:
        raise ConfigError("Contesto incompleto: slug mancante", slug=None)
    return slug_value


def _require_repo_root_dir(context: _Ctx, *, slug: str) -> Path:
    try:
        repo_root = context.repo_root_dir
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise PipelineError("Contesto incompleto: repo_root_dir mancante", slug=slug) from exc
    if repo_root is None:
        raise PipelineError("Contesto incompleto: repo_root_dir mancante", slug=slug)
    return Path(repo_root)


def _require_config_dir(context: _Ctx, *, slug: str) -> Path:
    try:
        config_dir = context.config_dir
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise ConfigError("Contesto incompleto: config_dir mancante", slug=slug) from exc
    if config_dir is None:
        raise ConfigError("Contesto incompleto: config_dir mancante", slug=slug)
    return Path(config_dir)


def load_semantic_mapping(context: _Ctx, logger: Optional[logging.Logger] = None) -> Dict[str, List[str]]:
    """Carica e normalizza il mapping semantico per il cliente corrente."""
    logger = logger or get_structured_logger("semantic.mapping", context=context)

    slug = _require_slug(context)
    repo_root = _require_repo_root_dir(context, slug=slug)
    config_dir = _require_config_dir(context, slug=slug)

    from pipeline.yaml_utils import yaml_read

    candidates = iter_mapping_candidates(
        context_slug=slug,
        config_dir=config_dir,
        repo_root_dir=repo_root,
        repo_default_dir=repo_root,
        mapping_filename=SEMANTIC_MAPPING_FILE,
    )

    for source, repo_root_dir, file_path in candidates:
        try:
            result = load_mapping_file(
                repo_root_dir=repo_root_dir,
                file_path=file_path,
                slug=slug,
                yaml_read=yaml_read,
                source=source,
            )
        except FileNotFoundError:
            logger.info(
                "semantic.mapping.missing_candidate",
                extra={
                    "slug": slug,
                    "source": source,
                    "file_path": str(file_path),
                },
            )
            continue
        except ConfigError as exc:
            logger.warning(
                "semantic.mapping.invalid",
                extra={
                    "slug": slug,
                    "source": source,
                    "file_path": str(file_path),
                    "error": str(exc),
                },
            )
            if source == "workspace":
                raise
            if source == "fallback":
                raise
            continue
        except PipelineError:
            raise
        except Exception as exc:
            logger.warning(
                "semantic.mapping.load_failed",
                extra={
                    "slug": slug,
                    "source": source,
                    "file_path": str(file_path),
                    "error": str(exc),
                },
            )
            continue

        if result.mapping:
            logger.info(
                "semantic.mapping.loaded",
                extra={
                    "slug": slug,
                    "source": result.source,
                    "file_path": str(result.path),
                    "concepts": len(result.mapping),
                },
            )
            return cast(Dict[str, List[str]], result.mapping)

        logger.warning(
            "semantic.mapping.empty_candidate",
            extra={
                "slug": slug,
                "source": result.source,
                "file_path": str(result.path),
            },
        )

    logger.error("semantic.mapping.not_found", extra={"slug": slug})
    raise ConfigError("Nessun mapping semantico disponibile.", slug=slug)
