# tests/test_vision_to_mapping.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

import semantic.api as sapi
from pipeline.exceptions import ConfigError


@dataclass
class C:
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str


def _ctx(base: Path) -> C:
    return C(
        base_dir=base,
        raw_dir=base / "raw",
        md_dir=base / "book",
        slug="e2e",
    )


def _write_vision_yaml(config_dir: Path) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    vision_yaml = config_dir / "vision_statement.yaml"
    # Contenuto minimale ma rappresentativo delle sezioni supportate
    payload = {
        "ethical_framework": [
            "Fairness",
            "Privacy",
            "fairness",
        ],  # 'fairness' duplicato (case-insensitive)
        "uvp": ["Speed", "Reliability"],
        "key_metrics": ["NPS", "Time-to-Value"],
        "risks_mitigations": ["Bias", "Drift"],
        "operating_model": ["Hub-and-Spoke"],
        "architecture_principles": ["APIs first"],
        "ethics_governance_tools": ["Model Cards"],
        "stakeholders_impact": ["Employees", "Customers"],
        "goals": {
            "general": ["Grow", "Scale"],
            "baskets": {
                "b3": ["Quick Wins"],
                "b6": ["Stabilize"],
                "b12": ["Transform"],
            },
        },
    }
    vision_yaml.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )
    return vision_yaml


def test_build_mapping_from_vision_happy_path(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    cfg = base / "config"
    _write_vision_yaml(cfg)

    ctx = _ctx(base)
    logger = logging.getLogger("test")

    mapping_path = sapi.build_mapping_from_vision(cast(Any, ctx), logger, slug=ctx.slug)
    assert mapping_path.exists()
    assert mapping_path.parent == cfg

    # Verifica che il mapping contenga le chiavi attese e che i duplicati siano deduplicati
    data = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    assert "ethical_framework" in data
    assert data["ethical_framework"] == [
        "Fairness",
        "Privacy",
    ]  # 'fairness' dedup (case-insensitive)
    # Goals esplosi nelle chiavi specifiche
    assert "goals_general" in data and data["goals_general"] == ["Grow", "Scale"]
    assert "goals_b3" in data and data["goals_b3"] == ["Quick Wins"]
    assert "goals_b6" in data and data["goals_b6"] == ["Stabilize"]
    assert "goals_b12" in data and data["goals_b12"] == ["Transform"]


def test_build_mapping_from_vision_raises_without_yaml(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    cfg = base / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    # Non scriviamo vision_statement.yaml → deve sollevare ConfigError
    ctx = _ctx(base)
    logger = logging.getLogger("test")
    try:
        sapi.build_mapping_from_vision(cast(Any, ctx), logger, slug=ctx.slug)
    except ConfigError as e:
        # Deve includere il path del file mancante
        assert "vision_statement.yaml" in str(e)
    else:
        raise AssertionError("build_mapping_from_vision doveva sollevare ConfigError")
