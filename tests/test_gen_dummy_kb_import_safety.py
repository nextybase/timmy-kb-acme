# SPDX-License-Identifier: GPL-3.0-only
# tests/test_gen_dummy_kb_import_safety.py
from __future__ import annotations

import importlib
import sys

import tools.gen_dummy_kb as gen_dummy_mod
from tools.gen_dummy_kb import main as gen_dummy_main
from ui.utils.workspace import clear_base_cache


def _stub_minimal_environment(monkeypatch, tmp_path, *, run_vision_return=None) -> None:
    monkeypatch.setattr(gen_dummy_mod, "ensure_local_workspace_for_ui", lambda **_: None)
    monkeypatch.setattr(gen_dummy_mod, "_client_base", lambda slug: tmp_path / f"timmy-kb-{slug}")
    monkeypatch.setattr(gen_dummy_mod, "_pdf_path", lambda slug: tmp_path / "VisionStatement.pdf")
    base_dir = tmp_path / "timmy-kb-dummy"
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "semantic").mkdir(parents=True, exist_ok=True)
    (base_dir / "book").mkdir(parents=True, exist_ok=True)
    (base_dir / "raw").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "config.yaml").write_text("dummy: true\n", encoding="utf-8")
    (base_dir / "semantic" / "semantic_mapping.yaml").write_text("", encoding="utf-8")
    (base_dir / "semantic" / "cartelle_raw.yaml").write_text("", encoding="utf-8")
    (base_dir / "semantic" / "tags.db").write_bytes(b"")
    (base_dir / "book" / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (base_dir / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (base_dir / "raw" / "sample.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    if run_vision_return is None:
        monkeypatch.setattr(gen_dummy_mod, "run_vision", lambda *a, **k: None)
    else:
        monkeypatch.setattr(gen_dummy_mod, "run_vision", run_vision_return)
    if run_vision_return is None:
        monkeypatch.setattr(gen_dummy_mod, "_run_vision_with_timeout", lambda **_: (True, None))
    else:
        monkeypatch.setattr(gen_dummy_mod, "_run_vision_with_timeout", lambda **_: (False, {"error": "boom"}))
    monkeypatch.setattr(gen_dummy_mod, "_call_drive_min", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_mod, "_call_drive_build_from_mapping", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_mod, "_write_basic_semantic_yaml", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_mod, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_mod, "_validate_dummy_structure", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_mod, "safe_write_text", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_mod, "safe_write_bytes", lambda *a, **k: None)
    monkeypatch.setenv("REPO_ROOT_DIR", str(base_dir))
    monkeypatch.setattr(gen_dummy_mod, "REPO_ROOT", base_dir)
    monkeypatch.setattr(gen_dummy_mod, "_purge_previous_state", lambda *a, **k: None)


def test_module_import_has_no_side_effects(tmp_path):
    """Importare il modulo non deve modificare sys.path né fare I/O."""
    before = list(sys.path)
    mod = importlib.import_module("tools.gen_dummy_kb")

    # Nessuna mutazione a import-time
    assert before == sys.path

    # Placeholders non risolti finché non si chiama _ensure_dependencies()
    assert getattr(mod, "safe_write_text") is None
    assert getattr(mod, "safe_write_bytes") is None


def test_ensure_dependencies_is_idempotent(monkeypatch, tmp_path):
    """_ensure_dependencies resta idempotente e non tocca sys.path."""
    mod = importlib.import_module("tools.gen_dummy_kb")

    before = list(sys.path)

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

    monkeypatch.setitem(sys.modules, "pipeline.file_utils", _PFU)
    monkeypatch.setitem(sys.modules, "pipeline.logging_utils", _PLU)
    monkeypatch.setitem(sys.modules, "pipeline.path_utils", _PPU)
    monkeypatch.setitem(sys.modules, "semantic.auto_tagger", _SAT)
    monkeypatch.setitem(sys.modules, "semantic.config", _SC)
    monkeypatch.setitem(sys.modules, "semantic.normalizer", _SN)
    monkeypatch.setitem(sys.modules, "semantic.tags_io", _STIO)

    mod._ensure_dependencies()
    first_path = list(sys.path)
    mod._ensure_dependencies()
    second_path = list(sys.path)

    # Nessuna mutazione di sys.path e placeholder popolati
    assert before == first_path == second_path
    assert mod.safe_write_text is not None
    assert mod.safe_write_bytes is not None


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
