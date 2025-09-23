from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline.exceptions import ConfigError
from semantic import api as sapi


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


class _NoopLogger:
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def debug(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_only_unsafe_pdfs_raise_explicit_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = _NoopLogger()

    ctx.raw_dir.mkdir(parents=True, exist_ok=True)
    ctx.md_dir.mkdir(parents=True, exist_ok=True)

    # Crea PDF finti
    (ctx.raw_dir / "a.pdf").write_bytes(b"%PDF-1.4\n%\n")
    (ctx.raw_dir / "b.pdf").write_bytes(b"%PDF-1.4\n%\n")

    # Qualsiasi verifica path-safety fallisce -> tutti scartati
    from pipeline import path_utils as ppath

    def _always_unsafe(*_a: Any, **_k: Any):
        raise ConfigError("unsafe")

    monkeypatch.setattr(ppath, "ensure_within_and_resolve", _always_unsafe, raising=True)

    with pytest.raises(ConfigError) as ei:
        sapi.convert_markdown(ctx, logger=logger, slug=ctx.slug)

    msg = str(ei.value)
    assert "non sicuri" in msg or "fuori perimetro" in msg
    assert Path(getattr(ei.value, "file_path", "")) == ctx.raw_dir


def test_mixed_unsafe_and_valid_pdfs_processes_valid_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = _NoopLogger()

    ctx.raw_dir.mkdir(parents=True, exist_ok=True)
    ctx.md_dir.mkdir(parents=True, exist_ok=True)

    pdf_good = ctx.raw_dir / "good.pdf"
    pdf_bad = ctx.raw_dir / "bad.pdf"
    pdf_good.write_bytes(b"%PDF-1.4\n%\n")
    pdf_bad.write_bytes(b"%PDF-1.4\n%\n")

    # Simula path-safety: good = ok, bad = unsafe
    from pipeline import path_utils as ppath

    real_ensure = ppath.ensure_within_and_resolve

    def _guard(base: Path, p: Path):  # type: ignore[override]
        if p.name == "bad.pdf":
            raise ConfigError("unsafe")
        return real_ensure(base, p)

    monkeypatch.setattr(ppath, "ensure_within_and_resolve", _guard, raising=True)

    # Evita conversione reale; prepara un MD finto per simulare l'output
    (ctx.md_dir / "doc.md").write_text("# Doc\n", encoding="utf-8")
    monkeypatch.setattr(sapi, "_call_convert_md", lambda *a, **k: None, raising=True)

    mds = sapi.convert_markdown(ctx, logger=logger, slug=ctx.slug)
    names = {p.name for p in mds}
    assert "doc.md" in names
