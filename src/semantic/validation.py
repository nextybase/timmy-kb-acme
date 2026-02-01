# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Dict, Optional, cast

from pipeline.exceptions import ConfigError
from pipeline.path_utils import is_valid_slug

__all__ = ["validate_context_slug"]


def _maybe_raise(message: str, *, payload_slug: Optional[str]) -> None:
    """Alza ConfigError includendo lo slug del payload se disponibile.

    Nessun side-effect; funzione interna per mantenere il codice compatto e difensivo.
    """

    if payload_slug:
        raise ConfigError(message, slug=payload_slug)
    raise ConfigError(message)


def validate_context_slug(data: Dict[str, Any], expected_slug: str) -> None:
    """Valida coerenza e formato dello slug presente in `data['context']`.

    Requisiti:
    - `data` è un dict
    - `data['context']` è un dict
    - `context['slug']` è una stringa non vuota, valida secondo `is_valid_slug`
      e uguale a `expected_slug`.

    In caso di violazione solleva sempre `ConfigError` (mai KeyError/AttributeError).
    Se disponibile include lo slug del payload in `ConfigError(slug=...)`.
    """

    if not isinstance(data, dict):
        _maybe_raise("Output modello non valido: payload non è un oggetto JSON.", payload_slug=None)

    ctx = data.get("context")
    if not isinstance(ctx, dict):
        _maybe_raise("Output modello non valido: 'context' deve essere un oggetto.", payload_slug=None)

    ctx_dict = cast(Dict[str, Any], ctx)
    raw_slug = ctx_dict.get("slug")
    payload_slug = raw_slug.strip() if isinstance(raw_slug, str) else ""
    if not payload_slug:
        _maybe_raise("Output modello non valido: 'context.slug' mancante o non stringa.", payload_slug=None)

    if not is_valid_slug(payload_slug):
        _maybe_raise(
            "Output modello non valido: 'context.slug' non rispetta il formato richiesto.",
            payload_slug=payload_slug,
        )

    if payload_slug != expected_slug:
        _maybe_raise(
            f"Slug incoerente nel payload: {payload_slug!r} != {expected_slug!r}",
            payload_slug=payload_slug,
        )
