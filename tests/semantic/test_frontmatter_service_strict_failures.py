# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.frontmatter_utils import read_frontmatter
from semantic import frontmatter_service as front
from tests.support.contexts import TestClientCtx
from tests.utils.workspace import ensure_minimal_workspace_layout


def _ctx(base: Path) -> TestClientCtx:
    return TestClientCtx(
        slug="dummy",
        repo_root_dir=base,
        semantic_dir=base / "semantic",
        config_dir=base / "config",
    )


def _prepare_workspace(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "output" / "timmy-kb-dummy"
    ensure_minimal_workspace_layout(base, client_name="dummy")
    mapping = base / "semantic" / "semantic_mapping.yaml"
    mapping.write_text("{}\n", encoding="utf-8")
    md_path = base / "book" / "a.md"
    md_path.write_text("---\ntitle:\n---\ncontenuto\n", encoding="utf-8")
    return base, md_path


def test_enrich_frontmatter_hard_fails_on_markdown_read_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base, _md_path = _prepare_workspace(tmp_path)

    def _boom_read(*_args: object, **_kwargs: object) -> tuple[dict[str, object], str]:
        raise OSError("boom-read")

    monkeypatch.setattr("pipeline.frontmatter_utils.read_frontmatter", _boom_read)

    with pytest.raises(PipelineError, match="Frontmatter read failed for slug=dummy"):
        front.enrich_frontmatter(
            _ctx(base),
            logging.getLogger("test.frontmatter.read_fail"),
            {"a": {"aliases": []}},
            slug="dummy",
        )


def test_enrich_frontmatter_hard_fails_on_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base, _md_path = _prepare_workspace(tmp_path)

    def _boom_cfg(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("bad-config")

    monkeypatch.setattr(front, "load_semantic_config", _boom_cfg)

    with pytest.raises(ConfigError, match="Semantic config load failed for slug=dummy"):
        front.enrich_frontmatter(
            _ctx(base),
            logging.getLogger("test.frontmatter.cfg_fail"),
            {"a": {"aliases": []}},
            slug="dummy",
        )


def test_enrich_frontmatter_ok_updates_markdown(tmp_path: Path) -> None:
    base, md_path = _prepare_workspace(tmp_path)

    touched = front.enrich_frontmatter(
        _ctx(base),
        logging.getLogger("test.frontmatter.ok"),
        {"a": {"aliases": []}},
        slug="dummy",
    )

    assert md_path in touched
    meta, body = read_frontmatter(base / "book", md_path, encoding="utf-8", use_cache=False)
    assert meta.get("title") == "a"
    assert "a" in (meta.get("tags") or [])
    assert "contenuto" in body
