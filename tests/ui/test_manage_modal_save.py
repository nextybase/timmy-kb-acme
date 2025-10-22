# tests/ui/test_manage_modal_save.py
from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Callable

import pytest


def _build_streamlit_stub(save_button_pressed: bool = True) -> Any:
    """Stub minimale di Streamlit sufficiente a importare ui.pages.manage e
    a far eseguire _open_tags_editor_modal con il click su 'Salva'."""

    class _Col:
        def __init__(self, save_pressed: bool) -> None:
            self._save_pressed = save_pressed

        def button(self, label: str, *args: Any, **kwargs: Any) -> bool:
            # Nel modal ci sono due pulsanti: 'Salva' e 'Chiudi'
            if label == "Salva":
                return self._save_pressed
            return False

    class _DialogRunner:
        def __init__(self, fn: Callable[[], None]) -> None:
            self._fn = fn

        def __call__(self) -> None:
            # Esegue direttamente il body del modal
            self._fn()

    from tests.ui.streamlit_stub import StreamlitStub

    module = StreamlitStub()
    module.register_button_sequence("Salva", [save_button_pressed])
    module.register_button_sequence("Chiudi", [False])

    def dialog(_title: str, **_kwargs: Any) -> Callable[[Callable[[], None]], _DialogRunner]:
        def _wrap(fn: Callable[[], None]) -> _DialogRunner:
            return _DialogRunner(fn)

        return _wrap

    def text_area(*_a: Any, **_k: Any) -> str:
        # YAML valido
        return "version: 2\nkeep_only_listed: true\ntags: []\n"

    def columns(_n: int | list[int]) -> tuple[_Col, _Col]:
        return _Col(save_button_pressed), _Col(save_button_pressed)

    def _no_op(*_a: Any, **_k: Any) -> None:
        return None

    def _button(*_a: Any, **_k: Any) -> bool:
        return False

    def selectbox(*_a: Any, **_k: Any) -> str:
        return "stub"

    sys_modules = {}

    return module, sys_modules


@pytest.fixture(autouse=True)
def patch_streamlit_before_import(monkeypatch: pytest.MonkeyPatch) -> None:
    # Inseriamo lo stub PRIMA di importare manage.py
    import sys

    module, submodules = _build_streamlit_stub(save_button_pressed=True)
    monkeypatch.setitem(sys.modules, "streamlit", module)
    for name, mod in submodules.items():
        monkeypatch.setitem(sys.modules, name, mod)
    fake_chrome = types.ModuleType("ui.chrome")
    fake_chrome.render_chrome_then_require = lambda **_kwargs: "acme"  # type: ignore[attr-defined]
    fake_clients_store = types.ModuleType("ui.clients_store")
    fake_clients_store.get_state = lambda slug: "ready"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ui.chrome", fake_chrome)
    monkeypatch.setitem(sys.modules, "ui.clients_store", fake_clients_store)


def test_modal_save_uses_path_safety(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture):
    # Import tardivo dopo aver registrato lo stub streamlit

    # Stub: workspace_root → directory di test
    base_dir = tmp_path / "output" / "timmy-kb-dummy"
    (base_dir / "semantic").mkdir(parents=True)

    import ui.pages.manage as manage  # type: ignore

    # Monkeypatch workspace root per evitare dipendenze da resolve_raw_dir
    monkeypatch.setattr(manage, "_workspace_root", lambda slug: base_dir, raising=True)

    # Tracciamo la chiamata a ensure_within_and_resolve
    called_args: list[tuple[Path, Path]] = []

    def _ensure_within_and_resolve(root: Path, candidate: Path) -> Path:
        called_args.append((root, candidate))
        # restituiamo il candidate (simuliamo risoluzione ok)
        return candidate

    monkeypatch.setattr(manage, "ensure_within_and_resolve", _ensure_within_and_resolve, raising=True)

    # Intercettiamo la write
    saved: dict[str, Any] = {}

    def _safe_write_text(path: Path, content: str, **_kw: Any) -> None:
        saved["path"] = path
        saved["content"] = content

    monkeypatch.setattr(manage, "safe_write_text", _safe_write_text, raising=True)

    # Evitiamo IO iniziale
    monkeypatch.setattr(
        manage, "read_text_safe", lambda *_a, **_k: "version: 2\nkeep_only_listed: true\ntags: []\n", raising=True
    )

    caplog.set_level("INFO")

    # Eseguiamo il modal (simula click su "Salva")
    manage._open_tags_editor_modal("acme")

    # Asserzioni: ensure_within_and_resolve chiamato con base_dir e semantic/tags_reviewed.yaml
    assert called_args, "ensure_within_and_resolve non è stato chiamato"
    root_arg, candidate_arg = called_args[0]
    assert root_arg == base_dir
    assert candidate_arg == base_dir / "semantic" / "tags_reviewed.yaml"

    # E safe_write_text deve ricevere il path 'risolto'
    assert Path(saved["path"]) == candidate_arg
    assert "version:" in saved["content"]

    # Log strutturati presenti
    events = [rec.message for rec in caplog.records]
    assert any("ui.manage.tags.open" in e for e in events)
    assert any("ui.manage.tags.save" in e for e in events)
