# tests/test_semantic_extractor_punct_matching.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from semantic.semantic_extractor import extract_semantic_concepts


class Ctx:
    # Annotazioni allineate al Protocol _Ctx
    base_dir: Path
    md_dir: Path
    slug: Optional[str]
    config_dir: Optional[Path]
    repo_root_dir: Optional[Path]

    def __init__(self, base: Path, md: Path) -> None:
        self.base_dir = base
        self.md_dir = md
        self.slug = "x"  # Optional[str] → ok anche se assegniamo una str
        self.config_dir = base / "config"
        self.repo_root_dir = base  # Optional[Path] → ok


def test_extractor_matches_punctuated_keywords(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "kb"
    md = base / "book"
    base.mkdir()
    md.mkdir()
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

    import semantic.semantic_extractor as se

    monkeypatch.setattr(se, "load_semantic_mapping", fake_load_mapping)

    ctx = Ctx(base, md)
    out = extract_semantic_concepts(ctx, logging.getLogger("t"))
    assert "c++" in out and any(m["file"] == "cxx.md" for m in out["c++"])
    assert "ml/ops" in out and any(m["file"] == "mlops.md" for m in out["ml/ops"])
    assert "data+" in out and any(m["file"] == "data_plus.md" for m in out["data+"])
