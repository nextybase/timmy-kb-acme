# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

from tests.support.contexts import TestClientCtx

import pipeline.content_utils as cu


def _ctx(base: Path, book: Path) -> TestClientCtx:
    return TestClientCtx(
        slug="dummy",
        base_dir=base,
        repo_root_dir=base,
        raw_dir=base / "raw",
        md_dir=book,
        semantic_dir=base / "semantic",
        config_dir=base / "config",
    )


def test_readme_and_summary_respect_mapping(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    raw = base / "raw"
    config_dir = base / "config"
    semantic_dir = base / "semantic"

    book.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    mapping_yaml = "areas:\n" "  - key: area-uno\n" "    descrizione: Descrizione Area Uno\n"
    (semantic_dir / "semantic_mapping.yaml").write_text(mapping_yaml, encoding="utf-8")

    # Prepara una struttura book con markdown annidato
    area_dir = book / "area-uno"
    area_dir.mkdir(parents=True, exist_ok=True)
    (area_dir / "doc.md").write_text("---\ntitle: Doc\n---\nBody\n", encoding="utf-8")

    ctx = _ctx(base, book)

    readme_path = cu.generate_readme_markdown(ctx)
    summary_path = cu.generate_summary_markdown(ctx)

    readme = readme_path.read_text(encoding="utf-8")
    summary = summary_path.read_text(encoding="utf-8")

    assert "## Area Uno" in readme
    assert "Descrizione Area Uno" in readme
    assert "- [Doc](area-uno/doc.md)" in summary


def test_readme_includes_entity_table(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    config_dir = base / "config"
    semantic_dir = base / "semantic"

    book.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    mapping_yaml = (
        "areas:\n"
        "  - key: area-uno\n"
        "    descrizione: Descrizione Area Uno\n"
        "entity_to_area:\n"
        "  Progetto: area-uno\n"
    )
    (semantic_dir / "semantic_mapping.yaml").write_text(mapping_yaml, encoding="utf-8")

    ctx = _ctx(base, book)
    readme_path = cu.generate_readme_markdown(ctx)
    content = readme_path.read_text(encoding="utf-8")

    assert "## Entità rilevanti per il tuo dominio" in content
    assert "| Progetto |" in content
    assert "PRJ-" in content
