# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from pipeline.path_utils import to_kebab_strict
from pipeline.semantic_mapping_utils import raw_categories_from_semantic_mapping
from semantic.vision_utils import vision_to_semantic_mapping_yaml


def _vision_payload() -> Dict[str, Any]:
    return {
        "status": "ok",
        "areas": [
            {
                "key": "automation-engineering",
                "ambito": "Design",
                "descrizione_breve": "Blueprint",
                "documents": ["doc1.pdf"],
                "artefatti": ["artifactA"],
                "correlazioni": {"entities": [{"name": "entity1", "category": "automation-engineering"}]},
            },
            {
                "key": "business-ops",
                "ambito": "Operations",
                "descrizione_breve": "Operations team",
                "documents": ["process.pdf"],
                "artefatti": [],
            },
            {
                "key": "customer-success",
                "ambito": "Customer",
                "descrizione_breve": "Support",
                "documents": [],
                "artefatti": [],
            },
        ],
        "system_folders": {"identity": {}, "glossario": {}},
    }


@pytest.mark.parametrize(
    "slug",
    ["client-alpha", "beta-123"],
)
def test_raw_categories_follow_vision_contract(tmp_path: Path, slug: str) -> None:
    payload = _vision_payload()
    yaml_serialized = vision_to_semantic_mapping_yaml(payload, slug=slug)
    mapping_path = tmp_path / "semantic_mapping.yaml"
    mapping_path.write_text(yaml_serialized, encoding="utf-8")

    categories = raw_categories_from_semantic_mapping(semantic_dir=tmp_path, mapping_path=mapping_path)
    expected = sorted(
        to_kebab_strict(area["key"], context="tests.test_semantic_mapping_contract") for area in payload["areas"]
    )
    assert categories == expected
