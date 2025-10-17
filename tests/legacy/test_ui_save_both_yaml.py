from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from pipeline.exceptions import ConfigError


class _DummyCtx:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # pragma: no cover - simple stub
        return False


class _DummySt:
    def __init__(self, slug: str, vision_state: Dict[str, Any], overrides: Dict[str, str] | None = None):
        self.session_state: Dict[str, Any] = {"slug": slug, "vision_workflow": vision_state}
        self._overrides = overrides or {}

    # Layout helpers
    def columns(self, _spec) -> Tuple[_DummyCtx, _DummyCtx, _DummyCtx]:  # type: ignore[name-defined]
        return _DummyCtx(), _DummyCtx(), _DummyCtx()

    def markdown(self, *_a, **_k) -> None:  # pragma: no cover
        pass

    def json(self, *_a, **_k) -> None:  # pragma: no cover
        pass

    # Inputs
    def text_input(self, _label: str, value: str = "", **_k) -> str:
        return value

    def button(self, *_a, **_k) -> bool:
        return False

    def file_uploader(self, *_a, **_k):  # pragma: no cover
        return None

    # Form API
    def form(self, _name: str) -> _DummyCtx:  # type: ignore[name-defined]
        return _DummyCtx()

    def text_area(self, label: str, value: str = "", **_k) -> str:
        return self._overrides.get(label, value)

    def form_submit_button(self, _label: str) -> bool:
        return True

    # Messages
    def success(self, *_a, **_k) -> None:  # pragma: no cover
        pass

    def warning(self, *_a, **_k) -> None:  # pragma: no cover
        pass

    def error(self, message: str) -> None:
        # Re-propaga come ConfigError per consentire pytest.raises
        raise ConfigError(message)

    # Session/flow
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
            "mapping": str(sem_dir / "semantic_mapping.yaml"),
            "cartelle_raw": str(sem_dir / "cartelle_raw.yaml"),
        },
        # Valori usati come fallback se lettura fallisce
        "mapping_yaml": "",
        "cartelle_yaml": "",
    }


def test_ui_save_yaml_mismatch_slug_hard_fail(monkeypatch, tmp_path):
    # Arrange: stato UI con workspace esistente e file su disco
    vision_state = _setup_state(tmp_path)
    slug = "acme"

    # Override dei contenuti editati dall'utente (mismatch nello slug del mapping)
    overrides = {
        "semantic/semantic_mapping.yaml": "context:\n  slug: other\n",
        "semantic/cartelle_raw.yaml": "context:\n  slug: acme\n",
    }
    dummy_st = _DummySt(slug, vision_state, overrides)

    # Import e patch del modulo UI
    import importlib

    ui_mod = importlib.import_module("src.ui.landing_slug".replace("/", ".").replace("\\", "."))
    monkeypatch.setattr(ui_mod, "st", dummy_st, raising=True)

    # Salva contenuto originale per verifica che non cambi
    mapping_file = Path(vision_state["yaml_paths"]["mapping"])
    cart_file = Path(vision_state["yaml_paths"]["cartelle_raw"])
    orig_mapping = mapping_file.read_text(encoding="utf-8")
    orig_cart = cart_file.read_text(encoding="utf-8")

    # Act + Assert: hard-fail con ConfigError e nessuna scrittura
    with pytest.raises(ConfigError):
        ui_mod.render_landing_slug(None)

    assert mapping_file.read_text(encoding="utf-8") == orig_mapping
    assert cart_file.read_text(encoding="utf-8") == orig_cart


def test_ui_save_yaml_cartelle_auto_heal_missing_context(monkeypatch, tmp_path):
    # Arrange: stato con workspace e file su disco
    vision_state = _setup_state(tmp_path)
    slug = "acme"

    # Cartelle senza context: deve essere auto-heal (iniezione context.slug)
    overrides = {
        "semantic/semantic_mapping.yaml": "context:\n  slug: acme\n",
        "semantic/cartelle_raw.yaml": "folders:\n  - key: foo\n",
    }
    dummy_st = _DummySt(slug, vision_state, overrides)

    import importlib

    ui_mod = importlib.import_module("src.ui.landing_slug".replace("/", ".").replace("\\", "."))
    monkeypatch.setattr(ui_mod, "st", dummy_st, raising=True)

    cart_file = Path(vision_state["yaml_paths"]["cartelle_raw"])

    # Act: submit salva senza errori e applica auto-heal
    ui_mod.render_landing_slug(None)

    # Assert: context.slug iniettato e coerente
    import yaml as _yaml

    data = _yaml.safe_load(cart_file.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("context", {}).get("slug") == slug


def test_ui_save_yaml_cartelle_slug_mismatch_hard_fail(monkeypatch, tmp_path):
    vision_state = _setup_state(tmp_path)
    slug = "acme"

    overrides = {
        "semantic/semantic_mapping.yaml": "context:\n  slug: acme\n",
        "semantic/cartelle_raw.yaml": "context:\n  slug: other\n",
    }
    dummy_st = _DummySt(slug, vision_state, overrides)

    import importlib

    ui_mod = importlib.import_module("src.ui.landing_slug".replace("/", ".").replace("\\", "."))
    monkeypatch.setattr(ui_mod, "st", dummy_st, raising=True)

    mapping_file = Path(vision_state["yaml_paths"]["mapping"])
    cart_file = Path(vision_state["yaml_paths"]["cartelle_raw"])
    orig_mapping = mapping_file.read_text(encoding="utf-8")
    orig_cart = cart_file.read_text(encoding="utf-8")

    import pytest

    from pipeline.exceptions import ConfigError

    with pytest.raises(ConfigError):
        ui_mod.render_landing_slug(None)

    assert mapping_file.read_text(encoding="utf-8") == orig_mapping
    assert cart_file.read_text(encoding="utf-8") == orig_cart
