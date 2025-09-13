import logging
from pathlib import Path


def _ctx(base_dir: Path):
    class C:
        pass

    c = C()
    c.base_dir = base_dir
    c.raw_dir = base_dir / "raw"
    c.md_dir = base_dir / "book"
    c.slug = "x"
    return c


def test_build_mapping_from_vision_happy_path(tmp_path):
    from semantic.api import build_mapping_from_vision

    base = tmp_path / "output" / "timmy-kb-x"
    cfg = base / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    # Vision YAML minimale
    (cfg / "vision_statement.yaml").write_text(
        """
meta:
  title: Demo
ethical_framework: [ Trasparenza, Affidabilità ]
goals:
  general:
    - Ridurre errori
    - Aumentare qualità
uvp:
  - Supporto 24/7
  - Esperienza utente migliorata
        """.strip(),
        encoding="utf-8",
    )

    p = build_mapping_from_vision(_ctx(base), logging.getLogger("test"), slug="x")
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "ethical_framework" in content
    assert "goals_general" in content
    assert "uvp" in content


def test_build_mapping_from_vision_raises_without_yaml(tmp_path):
    import pytest

    from semantic.api import build_mapping_from_vision

    base = tmp_path / "output" / "timmy-kb-x"
    (base / "config").mkdir(parents=True, exist_ok=True)

    with pytest.raises(Exception):
        build_mapping_from_vision(_ctx(base), logging.getLogger("test"), slug="x")
