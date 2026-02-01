# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any, Tuple

import pytest

import ui.utils.workspace
from pipeline.workspace_layout import WorkspaceLayout
from tests.ui.streamlit_stub import StreamlitStub


def register_streamlit_runtime(monkeypatch: pytest.MonkeyPatch, st_stub: StreamlitStub) -> None:
    """Registra moduli runtime di Streamlit necessari per i test UI."""

    def _cache_decorator(func=None, **_kwargs):
        def _wrap(inner):
            return inner

        if callable(func):
            return func
        return _wrap

    runtime_module = types.ModuleType("streamlit.runtime")
    caching_module = types.ModuleType("streamlit.runtime.caching")
    caching_module.cache_data = _cache_decorator  # type: ignore[attr-defined]
    caching_module.cache_resource = _cache_decorator  # type: ignore[attr-defined]
    caching_module.memoize = _cache_decorator  # type: ignore[attr-defined]

    scriptrunner_module = types.ModuleType("streamlit.runtime.scriptrunner")

    def _get_script_run_ctx(*_args: Any, **_kwargs: Any) -> None:
        return None

    scriptrunner_module.get_script_run_ctx = _get_script_run_ctx  # type: ignore[attr-defined]
    scriptrunner_module.script_run_context = types.SimpleNamespace(get_script_run_ctx=_get_script_run_ctx)  # type: ignore[attr-defined]

    script_runner_module = types.ModuleType("streamlit.runtime.scriptrunner.script_runner")

    class _RerunException(Exception):
        pass

    script_runner_module.RerunException = _RerunException  # type: ignore[attr-defined]

    scriptrunner_module.script_runner = script_runner_module  # type: ignore[attr-defined]
    runtime_module.caching = caching_module  # type: ignore[attr-defined]
    runtime_module.scriptrunner = scriptrunner_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "streamlit.runtime", runtime_module)
    monkeypatch.setitem(sys.modules, "streamlit.runtime.caching", caching_module)
    monkeypatch.setitem(sys.modules, "streamlit.runtime.scriptrunner", scriptrunner_module)
    monkeypatch.setitem(sys.modules, "streamlit.runtime.scriptrunner.script_runner", script_runner_module)
    setattr(st_stub, "runtime", runtime_module)


def _load_manage_module(
    monkeypatch: pytest.MonkeyPatch,
    st_stub: StreamlitStub,
    slug: str,
    has_normalized_result: Tuple[bool, str | None],
) -> None:
    monkeypatch.setitem(sys.modules, "streamlit", st_stub)
    register_streamlit_runtime(monkeypatch, st_stub)
    import ui.chrome
    import ui.utils.workspace

    monkeypatch.setattr(ui.chrome, "render_chrome_then_require", lambda *args, **kwargs: slug)
    base_dir = Path("output") / f"timmy-kb-{slug}"
    layout = WorkspaceLayout.from_workspace(workspace=base_dir, slug=slug)
    normalized_result_path = (
        Path(has_normalized_result[1]) if has_normalized_result[1] is not None else layout.normalized_dir
    )
    monkeypatch.setattr(
        ui.utils.workspace,
        "normalized_ready",
        lambda _slug: (has_normalized_result[0], normalized_result_path),
    )
    monkeypatch.setattr(
        ui.utils.workspace,
        "get_ui_workspace_layout",
        lambda _slug, require_drive_env=False: layout,
    )

    sys.modules.pop("ui.pages.manage", None)
    manage = importlib.import_module("ui.pages.manage")
    monkeypatch.setattr(manage, "_render_drive_tree", None, raising=False)
    monkeypatch.setattr(manage, "_render_drive_diff", None, raising=False)


def test_manage_semantic_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = StreamlitStub()
    normalized_path = str(Path("output") / "timmy-kb-dummy" / "normalized")
    _load_manage_module(monkeypatch, st_stub, slug="dummy", has_normalized_result=(True, normalized_path))

    assert any(label in st_stub.button_calls for label in ("Arricchimento semantico",))
    # Placeholder informativi disabilitati: nessun messaggio info/warning aggiuntivo
    assert not any("Arricchimento semantico" in msg for msg in st_stub.info_messages)
    assert not any("PDF rilevati" in msg for msg in st_stub.success_messages)
    unexpected_warn = "`semantic/tags.db` non trovato: estrai e valida i tag prima dell'arricchimento semantico."
    assert unexpected_warn not in st_stub.warning_messages


def test_iter_pdfs_safe_returns_resolved(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / "raw"
    root.mkdir(parents=True)
    pdf = root / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    try:
        (root / "link.pdf").symlink_to(pdf)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink non supportati su questa piattaforma: {exc}")
    results = list(ui.utils.workspace.iter_pdfs_safe(root))
    assert results == [pdf.resolve()]


def test_manage_tags_editor_syncs_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ui.pages import manage as manage_page

    st_stub = StreamlitStub()
    st_stub.register_button_sequence("Salva", [True])

    base_dir = tmp_path / "timmy-kb-dummy"
    semantic_dir = base_dir / "semantic"
    semantic_dir.mkdir(parents=True)
    (semantic_dir / "semantic_mapping.yaml").write_text("version: 1\n", encoding="utf-8")
    yaml_path = semantic_dir / "tags_reviewed.yaml"
    yaml_path.write_text("version: 2\nkeep_only_listed: true\ntags: []\n", encoding="utf-8")
    st_stub.session_state["tags_yaml_editor"] = yaml_path.read_text(encoding="utf-8")

    monkeypatch.setattr(manage_page, "st", st_stub)
    called: dict[str, Path] = {}

    def _fake_import(path: str | Path, **_kwargs):
        called["path"] = Path(path)
        return {}

    monkeypatch.setattr(manage_page, "import_tags_yaml_to_db", _fake_import)
    layout = WorkspaceLayout.from_workspace(workspace=base_dir, slug="dummy")

    manage_page._open_tags_editor_modal("dummy", layout=layout)

    assert called["path"] == yaml_path
    assert st_stub._rerun_called is True


def test_call_strict_matches_signature() -> None:
    from ui.pages import manage as manage_page

    def _fn(*, slug: str, overwrite: bool = False) -> tuple[str, bool]:
        return slug, overwrite

    result = manage_page._call_strict(_fn, slug="dummy", overwrite=True)
    assert result == ("dummy", True)


def test_call_strict_raises_on_mismatch() -> None:
    from ui.pages import manage as manage_page

    def _fn(slug: str, other: int) -> None:
        return None

    with pytest.raises(TypeError):
        manage_page._call_strict(_fn, slug="dummy")


def test_call_strict_rejects_unknown_kwargs() -> None:
    from ui.pages import manage as manage_page

    def _fn(slug: str, require_env: bool = False) -> tuple[str, bool]:
        return slug, require_env

    with pytest.raises(TypeError) as excinfo:
        manage_page._call_strict(_fn, slug="dummy", require_env=True, extra="nope")

    assert "Unknown kwargs" in str(excinfo.value)
