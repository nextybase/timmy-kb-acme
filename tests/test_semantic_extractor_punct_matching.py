# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_extractor_punct_matching.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from semantic.core import extract_semantic_concepts
from tests.utils.workspace import ensure_minimal_workspace_layout


class Ctx:
    # Annotazioni allineate al Protocol _Ctx
    base_dir: Path
    book_dir: Path
    slug: Optional[str]
    config_dir: Optional[Path]
    repo_root_dir: Optional[Path]

    def __init__(self, base: Path, md: Path) -> None:
        self.base_dir = base
        self.book_dir = md
        self.slug = "x"  # Optional[str] → ok anche se assegniamo una str
        self.config_dir = base / "config"
        self.repo_root_dir = base  # Optional[Path] → ok


def test_extractor_matches_punctuated_keywords(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    ensure_minimal_workspace_layout(base, client_name="x")
    (md / "cxx.md").write_text("intro to C++ basics", encoding="utf-8")
    (md / "mlops.md").write_text("we love ml/ops pipelines", encoding="utf-8")
    (md / "data_plus.md").write_text("this is data+ catalog", encoding="utf-8")

    # fissa il mapping senza passare da file YAML
    def fake_load_mapping(context, logger=None):
        return {
            "c++": ["c++"],
            "ml/ops": ["ml/ops", "ml ops"],
            "data+": ["data+", "data plus"],
        }

    import semantic.core as se

    monkeypatch.setattr(se, "load_semantic_mapping", fake_load_mapping)

    ctx = Ctx(base, md)
    out = extract_semantic_concepts(ctx)
    assert "c++" in out and any(m["file"] == "cxx.md" for m in out["c++"])
    assert "ml/ops" in out and any(m["file"] == "mlops.md" for m in out["ml/ops"])
    assert "data+" in out and any(m["file"] == "data_plus.md" for m in out["data+"])
