from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from pipeline.exceptions import ConfigError


class _DummyCtx:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # pragma: no cover
        return False


class _DummySt:
    def __init__(self, slug: str, vision_state: Dict[str, Any], overrides: Dict[str, str]):
        self.session_state: Dict[str, Any] = {"slug": slug, "vision_workflow": vision_state}
        self._overrides = overrides

    def columns(self, _spec) -> Tuple[_DummyCtx, _DummyCtx, _DummyCtx]:  # type: ignore[name-defined]
        return _DummyCtx(), _DummyCtx(), _DummyCtx()

    def markdown(self, *_a, **_k) -> None:  # pragma: no cover
        pass

    def json(self, *_a, **_k) -> None:  # pragma: no cover
        pass

    def text_input(self, _label: str, value: str = "", **_k) -> str:
        return value

    def button(self, *_a, **_k) -> bool:
        return False

    def file_uploader(self, *_a, **_k):  # pragma: no cover
        return None

    def form(self, _name: str) -> _DummyCtx:  # type: ignore[name-defined]
        return _DummyCtx()

    def text_area(self, label: str, value: str = "", **_k) -> str:
        return self._overrides.get(label, value)

    def form_submit_button(self, _label: str) -> bool:
        return True

    def success(self, *_a, **_k) -> None:  # pragma: no cover
        pass

    def warning(self, *_a, **_k) -> None:  # pragma: no cover
        pass

    def error(self, message: str) -> None:
        raise ConfigError(message)

    def rerun(self) -> None:  # pragma: no cover
        pass


def _setup_state(tmp_path: Path, *, slug: str = "acme") -> Dict[str, Any]:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = sem_dir / "semantic_mapping.yaml"
    cartelle_path = sem_dir / "cartelle_raw.yaml"
    mapping_path.write_text("context:\n  slug: acme\n", encoding="utf-8")
    cartelle_path.write_text("context:\n  slug: acme\n", encoding="utf-8")
    return {
        "slug": slug,
        "client_name": slug,
        "verified": True,
        "needs_creation": False,
        "workspace_created": True,
        "base_dir": str(tmp_path),
        "yaml_paths": {
            "mapping": "semantic/semantic_mapping.yaml",
            "cartelle_raw": "semantic/cartelle_raw.yaml",
        },
        "mapping_yaml": "",
        "cartelle_yaml": "",
    }


@pytest.mark.parametrize(
    "override_mapping",
    [
        "context: 123\n",  # context non dict
        "context:\n  slug: \n",  # slug vuoto
        "context: {}\n",  # slug mancante
    ],
)
def test_ui_save_yaml_invalid_context_variants(monkeypatch, tmp_path, override_mapping: str):
    vision_state = _setup_state(tmp_path)
    slug = "acme"
    overrides = {
        "semantic/semantic_mapping.yaml": override_mapping,
        "semantic/cartelle_raw.yaml": "context:\n  slug: acme\n",
    }
    dummy_st = _DummySt(slug, vision_state, overrides)

    import importlib

    ui_mod = importlib.import_module("src.ui.landing_slug".replace("/", ".").replace("\\", "."))
    monkeypatch.setattr(ui_mod, "st", dummy_st, raising=True)

    mapping_file = Path(vision_state["base_dir"]) / vision_state["yaml_paths"]["mapping"]
    cart_file = Path(vision_state["base_dir"]) / vision_state["yaml_paths"]["cartelle_raw"]
    orig_mapping = mapping_file.read_text(encoding="utf-8")
    orig_cart = cart_file.read_text(encoding="utf-8")

    with pytest.raises(ConfigError):
        ui_mod.render_landing_slug(None)

    assert mapping_file.read_text(encoding="utf-8") == orig_mapping
    assert cart_file.read_text(encoding="utf-8") == orig_cart
