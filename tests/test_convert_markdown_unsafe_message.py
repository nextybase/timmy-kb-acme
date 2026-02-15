# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline.exceptions import ConfigError
from semantic import convert_service
from tests._helpers.noop_logger import NoopLogger


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.repo_root_dir = base
        self.base_dir = base
        self.normalized_dir = base / "normalized"
        self.book_dir = base / "book"
        self.slug = slug


def _write_minimal_layout(base: Path) -> None:
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: dummy\n", encoding="utf-8")
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "book" / "README.md").write_text("# Placeholder\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Placeholder\n", encoding="utf-8")
    (base / "normalized").mkdir(parents=True, exist_ok=True)


def test_only_unsafe_markdown_raise_explicit_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = NoopLogger()

    _write_minimal_layout(base)
    ctx.normalized_dir.mkdir(parents=True, exist_ok=True)
    ctx.book_dir.mkdir(parents=True, exist_ok=True)

    # Legacy markdown già presente nel book
    (ctx.book_dir / "legacy.md").write_text("# Legacy\n", encoding="utf-8")

    # Crea Markdown finti
    (ctx.normalized_dir / "a.md").write_text("# A\n", encoding="utf-8")
    (ctx.normalized_dir / "b.md").write_text("# B\n", encoding="utf-8")

    # Qualsiasi verifica path-safety fallisce -> tutti scartati
    from pipeline import path_utils as ppath

    def _always_unsafe(*_a: Any, **_k: Any):
        raise ConfigError("unsafe")

    def _fake_iter_safe_paths(
        root: Path,
        *,
        include_dirs: bool = False,
        include_files: bool = True,
        suffixes: tuple[str, ...] | None = None,
        on_skip=None,
    ):
        if on_skip:
            on_skip(root / "a.md", "unsafe")
            on_skip(root / "b.md", "unsafe")
        return iter(())

    monkeypatch.setattr(ppath, "ensure_within_and_resolve", _always_unsafe, raising=True)
    monkeypatch.setattr(ppath, "iter_safe_paths", _fake_iter_safe_paths, raising=True)

    with pytest.raises(ConfigError) as ei:
        convert_service.convert_markdown(ctx, logger=logger, slug=ctx.slug)

    msg = str(ei.value)
    assert "non sicuri" in msg or "fuori perimetro" in msg
    assert Path(getattr(ei.value, "file_path", "")) == ctx.normalized_dir


def test_mixed_unsafe_and_valid_markdown_processes_valid_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = NoopLogger()

    _write_minimal_layout(base)
    ctx.normalized_dir.mkdir(parents=True, exist_ok=True)
    ctx.book_dir.mkdir(parents=True, exist_ok=True)

    md_good = ctx.normalized_dir / "good.md"
    md_bad = ctx.normalized_dir / "bad.md"
    md_good.write_text("# Good\n", encoding="utf-8")
    md_bad.write_text("# Bad\n", encoding="utf-8")

    # Simula path-safety: good = ok, bad = unsafe
    from pipeline import path_utils as ppath

    def _fake_iter_safe_paths(
        root: Path,
        *,
        include_dirs: bool = False,
        include_files: bool = True,
        suffixes: tuple[str, ...] | None = None,
        on_skip=None,
    ):
        if on_skip:
            on_skip(root / "bad.md", "unsafe")
        yield md_good

    monkeypatch.setattr(ppath, "iter_safe_paths", _fake_iter_safe_paths, raising=True)

    mds = convert_service.convert_markdown(ctx, logger=logger, slug=ctx.slug)
    names = {p.name for p in mds}
    assert "good.md" in names
