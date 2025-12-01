# SPDX-License-Identifier: GPL-3.0-only
# tests/test_gen_dummy_kb_import_safety.py
from __future__ import annotations

import importlib
import sys

import src.tools.gen_dummy_kb as gen_dummy_mod
from src.tools.gen_dummy_kb import main as gen_dummy_main
from ui.utils.workspace import clear_base_cache


def _stub_minimal_environment(monkeypatch, tmp_path, *, run_vision_return=None) -> None:
    monkeypatch.setattr(gen_dummy_mod, "ensure_local_workspace_for_ui", lambda **_: None)
    monkeypatch.setattr(gen_dummy_mod, "_client_base", lambda slug: tmp_path / f"timmy-kb-{slug}")
    monkeypatch.setattr(gen_dummy_mod, "_pdf_path", lambda slug: tmp_path / "VisionStatement.pdf")
    if run_vision_return is None:
        monkeypatch.setattr(gen_dummy_mod, "run_vision", lambda *a, **k: None)
    else:
        monkeypatch.setattr(gen_dummy_mod, "run_vision", run_vision_return)
    monkeypatch.setattr(gen_dummy_mod, "_call_drive_min", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_mod, "_call_drive_build_from_mapping", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_mod, "_write_basic_semantic_yaml", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_mod, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_mod, "safe_write_text", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_mod, "safe_write_bytes", lambda *a, **k: None)
    monkeypatch.setenv("REPO_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(gen_dummy_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gen_dummy_mod, "SRC_ROOT", tmp_path / "src")


def test_module_import_has_no_side_effects(tmp_path):
    """Importare il modulo non deve modificare sys.path né fare I/O."""
    before = list(sys.path)
    mod = importlib.import_module("src.tools.gen_dummy_kb")

    # Nessuna mutazione a import-time
    assert before == sys.path

    # Placeholders non risolti finché non si chiama _ensure_dependencies()
    assert getattr(mod, "safe_write_text") is None
    assert getattr(mod, "safe_write_bytes") is None
    assert getattr(mod, "_fin_import_csv") is None


def test_ensure_dependencies_is_idempotent(monkeypatch, tmp_path):
    """_ensure_dependencies può essere chiamato più volte senza duplicare sys.path."""
    mod = importlib.import_module("src.tools.gen_dummy_kb")

    # Simula insert su sys.path e traccia le chiamate
    inserted: list[str] = []

    def insert_once(idx: int, path: str) -> None:  # noqa: ARG001
        inserted.append(path)
        if path not in sys.path:
            sys.path.insert(0, path)

    monkeypatch.setattr(mod, "SRC_ROOT", tmp_path / "src")

    # Usa un proxy list che permette di intercettare insert senza monkeypatchare un metodo built-in
    class _PathProxy(list):
        def insert(self, idx: int, path: str) -> None:  # type: ignore[override]
            # Traccia come nel test e poi chiama l'insert reale senza ricorsione
            inserted.append(path)
            if path not in self:
                super().insert(0, path)

    monkeypatch.setattr(sys, "path", _PathProxy())

    # Stub moduli referenziati in _ensure_dependencies (ridotti per rientrare nei 120 char)
    class _PFU:  # pipeline.file_utils
        safe_write_bytes = object()
        safe_write_text = object()

    class _PLU:  # pipeline.logging_utils
        get_structured_logger = object()
        tail_path = object()

    class _PPU:  # pipeline.path_utils
        ensure_within = object()
        ensure_within_and_resolve = object()
        open_for_read_bytes_selfguard = object()

    class _SAT:  # semantic.auto_tagger
        extract_semantic_candidates = object()
        render_tags_csv = object()

    class _SC:  # semantic.config
        load_semantic_config = object()

    class _SN:  # semantic.normalizer
        normalize_tags = object()

    class _STIO:  # semantic.tags_io
        write_tagging_readme = object()
        write_tags_review_stub_from_csv = object()

    class _FA:  # finance.api (opzionale)
        import_csv = object()

    monkeypatch.setitem(sys.modules, "pipeline.file_utils", _PFU)
    monkeypatch.setitem(sys.modules, "pipeline.logging_utils", _PLU)
    monkeypatch.setitem(sys.modules, "pipeline.path_utils", _PPU)
    monkeypatch.setitem(sys.modules, "semantic.auto_tagger", _SAT)
    monkeypatch.setitem(sys.modules, "semantic.config", _SC)
    monkeypatch.setitem(sys.modules, "semantic.normalizer", _SN)
    monkeypatch.setitem(sys.modules, "semantic.tags_io", _STIO)
    monkeypatch.setitem(sys.modules, "finance.api", _FA)

    mod._ensure_dependencies()
    first_len = len(sys.path)

    mod._ensure_dependencies()
    second_len = len(sys.path)

    # Nessun path duplicato e almeno un inserimento eseguito
    assert first_len == second_len
    assert inserted


def test_logs_use_namespaced_events(caplog, tmp_path, monkeypatch):
    caplog.set_level("INFO")
    _stub_minimal_environment(monkeypatch, tmp_path)
    args = ["--slug", "dummy", "--name", "Dummy", "--no-vision", "--no-drive"]
    try:
        exit_code = gen_dummy_main(args)
    finally:
        clear_base_cache()
    assert exit_code == 0
    assert any(rec.message.startswith("tools.gen_dummy_kb.") for rec in caplog.records)


def test_logs_namespaced_on_failure(caplog, tmp_path, monkeypatch):
    caplog.set_level("ERROR")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    _stub_minimal_environment(monkeypatch, tmp_path, run_vision_return=_boom)
    args = ["--slug", "dummy", "--name", "Dummy", "--no-drive"]
    try:
        exit_code = gen_dummy_main(args)
    finally:
        clear_base_cache()
    assert exit_code == 0
    assert any(rec.message == "tools.gen_dummy_kb.vision_fallback_error" for rec in caplog.records)
