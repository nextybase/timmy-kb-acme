from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline.exceptions import ConfigError
from semantic import api as sapi


class _Ctx:
    def __init__(self, base: Path, slug: str = "x"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


class _NoopLogger:
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def debug(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_convert_markdown_unsafe_pdfs_with_legacy_md_fail_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Struttura base: output/timmy-kb-x/{raw,book}
    base = tmp_path / "output" / "timmy-kb-x"
    ctx = _Ctx(base, slug="x")
    logger = _NoopLogger()

    # Crea legacy in book/ e un PDF finto in raw/
    ctx.md_dir.mkdir(parents=True, exist_ok=True)
    (ctx.md_dir / "legacy.md").write_text("# Legacy\n", encoding="utf-8")

    ctx.raw_dir.mkdir(parents=True, exist_ok=True)
    (ctx.raw_dir / "a.pdf").write_bytes(b"%PDF-1.4\n%\n")

    # Tutti i PDF sono considerati "non sicuri" (path fuori perimetro)
    from pipeline import path_utils as ppath

    def _always_unsafe(*_a: Any, **_k: Any):
        raise ConfigError("unsafe")

    monkeypatch.setattr(ppath, "ensure_within_and_resolve", _always_unsafe, raising=True)

    with pytest.raises(ConfigError) as ei:
        sapi.convert_markdown(ctx, logger=logger, slug=ctx.slug)

    # Opzionale: messaggio informativo
    msg = str(ei.value)
    assert ("non sicuri" in msg) or ("fuori perimetro" in msg) or ("unsafe" in msg)
