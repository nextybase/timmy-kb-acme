from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple


def _load_context_base_dir(slug: str) -> Optional[Path]:
    try:
        from pipeline.context import ClientContext
    except Exception:
        return None

    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    except Exception:
        return None

    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        return None
    return Path(base_dir)


def _fallback_base_dir(slug: str) -> Path:
    return Path("output") / f"timmy-kb-{slug}"


def resolve_raw_dir(slug: str) -> Path:
    slug_value = slug.strip().lower()
    if not slug_value:
        raise ValueError("Slug must be a non-empty string")
    base_dir = _load_context_base_dir(slug_value) or _fallback_base_dir(slug_value)
    return Path(base_dir) / "raw"


def has_raw_pdfs(slug: Optional[str]) -> Tuple[bool, Optional[Path]]:
    slug_value = (slug or "").strip().lower()
    if not slug_value:
        return False, None

    raw_dir = resolve_raw_dir(slug_value)
    if not raw_dir.is_dir():
        return False, raw_dir

    try:
        if next(raw_dir.rglob("*.pdf"), None) is None:
            return False, raw_dir
    except StopIteration:  # pragma: no cover - defensive guard
        return False, raw_dir
    except Exception:
        return False, raw_dir

    return True, raw_dir
