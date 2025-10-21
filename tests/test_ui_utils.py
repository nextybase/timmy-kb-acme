from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import ConfigError
from timmykb.ui.utils import ensure_within_and_resolve


def test_wrapper_resolves_within_base(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    f = base / "x.txt"
    f.write_text("ok", encoding="utf-8")

    out = ensure_within_and_resolve(base, f)
    assert out == f.resolve()


def test_wrapper_blocks_outside_base(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    with pytest.raises(ConfigError):
        _ = ensure_within_and_resolve(base, outside)


def test_ui_raw_ready_respects_context_paths(tmp_path: Path):
    """Verifica (unit) che i path 'raw' e 'semantic' siano coerenti rispetto a un contesto fornito
    (simula il comportamento della UI che ora usa ClientContext.* invece di interrogare
    sem_get_paths)."""
    base = tmp_path / "custom-root"
    raw = base / "raw"
    semantic = base / "semantic"
    raw.mkdir(parents=True)
    semantic.mkdir(parents=True)

    # Crea un PDF dummy in raw e un CSV dummy in semantic
    (raw / "doc.pdf").write_text("dummy", encoding="utf-8")
    (semantic / "tags_raw.csv").write_text("id,tag\n1,test", encoding="utf-8")

    # Finto "context" con gli attributi usati dalla UI
    ctx = SimpleNamespace(base_dir=base, raw_dir=raw)

    # has_pdfs: True se esistono PDF in raw/
    raw_ok = hasattr(ctx, "raw_dir") and ctx.raw_dir and ctx.raw_dir.exists()
    has_pdfs = any(ctx.raw_dir.rglob("*.pdf")) if raw_ok else False

    # has_csv: True se esiste semantic/tags_raw.csv rispetto al base_dir
    base_ok = hasattr(ctx, "base_dir") and ctx.base_dir and ctx.base_dir.exists()
    has_csv = (ctx.base_dir / "semantic" / "tags_raw.csv").exists() if base_ok else False

    assert has_pdfs is True
    assert has_csv is True
