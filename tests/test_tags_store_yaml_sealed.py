# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from storage import tags_store
from pipeline.exceptions import ConfigError


def test_yaml_import_and_parse_sealed(tmp_path: Path) -> None:
    yaml_path = tmp_path / "tags_reviewed.yaml"
    yaml_path.write_text("dummy: value", encoding="utf-8")

    with pytest.raises(ConfigError) as parsed_exc:
        tags_store.parse_yaml_safe(yaml_path)
    assert "Import YAML" in str(parsed_exc.value) or "non supportato" in str(parsed_exc.value)

    with pytest.raises(ConfigError) as import_exc:
        tags_store.import_tags_yaml_to_db(yaml_path)
    assert "Import YAML" in str(import_exc.value)

    assert not hasattr(tags_store, "yaml")
    assert not hasattr(tags_store, "_parse_yaml_minimal")
