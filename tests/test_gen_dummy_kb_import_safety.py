# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_gen_dummy_kb_import_safety.py
from __future__ import annotations

import importlib
import sys

import pipeline.raw_transform_service as _raw_transform_sale
import tools.gen_dummy_kb as gen_dummy_mod
from pipeline.raw_transform_service import STATUS_OK
from tools.gen_dummy_kb import main as gen_dummy_main
from ui.utils.workspace import clear_base_cache


def _stub_minimal_environment(monkeypatch, tmp_path, *, run_vision_return=None) -> None:
    monkeypatch.setattr(gen_dummy_mod, "ensure_local_workspace_for_ui", lambda **_: None)
    monkeypatch.setattr(gen_dummy_mod, "_client_base", lambda slug: tmp_path / f"timmy-kb-{slug}")
    # SpaCy non è il focus di questi test: bypassiamo l'hard check
    import tools.dummy.orchestrator as dummy_orch

    monkeypatch.setattr(dummy_orch, "_ensure_spacy_available", lambda policy: None)
    base_dir = tmp_path / "timmy-kb-dummy"
    monkeypatch.setattr(gen_dummy_mod, "_pdf_path", lambda slug: base_dir / "config" / "VisionStatement.pdf")
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (base_dir / "semantic").mkdir(parents=True, exist_ok=True)
    (base_dir / "book").mkdir(parents=True, exist_ok=True)
    (base_dir / "raw").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "config.yaml").write_text(
        "meta:\n  client_name: Dummy\nops:\n  log_level: INFO\nraw_ingest:\n  transformer_lock:\n    name: stub-transform\n    version: 0.0.1\n    ruleset_hash: stub-ruleset\n",
        encoding="utf-8",
    )
    (base_dir / "semantic" / "semantic_mapping.yaml").write_text("", encoding="utf-8")
    (base_dir / "semantic" / "tags.db").write_bytes(b"")
    (base_dir / "book" / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (base_dir / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (base_dir / "raw" / "sample.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    normalized_dir = base_dir / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    (normalized_dir / "sample.md").write_text("# normalized\n", encoding="utf-8")
    (normalized_dir / "INDEX.json").write_text(
        '[{"status":"OK","normalized_path":"sample.md","source_path":"raw/sample.pdf","transformer_name":"stub","transformer_version":"0.0","ruleset_hash":"stub","input_hash":"","output_hash":""}]',
        encoding="utf-8",
    )

    class _StubTransformService:
        transformer_name = "stub-transform"
        transformer_version = "0.0.1"
        ruleset_hash = "stub-ruleset"

        def transform(self, *, input_path, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("# normalized stub\n", encoding="utf-8")
            return _raw_transform_sale.RawTransformResult(
                status=STATUS_OK,
                output_path=output_path,
                transformer_name=self.transformer_name,
                transformer_version=self.transformer_version,
                ruleset_hash=self.ruleset_hash,
                error=None,
            )

    monkeypatch.setattr(
        _raw_transform_sale,
        "get_default_raw_transform_service",
        lambda: _StubTransformService(),
    )
    monkeypatch.setattr(
        "timmy_kb.cli.raw_ingest.get_default_raw_transform_service",
        lambda: _StubTransformService(),
    )
    if run_vision_return is None:
        monkeypatch.setattr(gen_dummy_mod, "run_vision", lambda *a, **k: None)
    else:
        monkeypatch.setattr(gen_dummy_mod, "run_vision", run_vision_return)
    if run_vision_return is None:
        monkeypatch.setattr(gen_dummy_mod, "_run_vision_with_timeout", lambda **_: (True, None))
    else:
        monkeypatch.setattr(gen_dummy_mod, "_run_vision_with_timeout", lambda **_: (False, {"error": "boom"}))
    monkeypatch.setattr(gen_dummy_mod, "_call_drive_min", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_mod, "_write_basic_semantic_yaml", lambda *a, **k: {})
    monkeypatch.setattr(gen_dummy_mod, "_register_client", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_mod, "_validate_dummy_structure", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_mod, "safe_write_text", lambda *a, **k: None)
    monkeypatch.setattr(gen_dummy_mod, "safe_write_bytes", lambda *a, **k: None)
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(base_dir))
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
    monkeypatch.setenv("VISION_MODE", "DEEP")
    base_dir = tmp_path / "timmy-kb-dummy"
    sentinel_path = base_dir / "semantic" / ".vision_hash"
    mapping_path = base_dir / "semantic" / "semantic_mapping.yaml"
    if sentinel_path.exists():
        sentinel_path.unlink()
    if mapping_path.exists():
        mapping_path.unlink()
    args = ["--slug", "dummy", "--name", "Dummy", "--no-drive"]
    try:
        exit_code = gen_dummy_main(args)
    finally:
        clear_base_cache()
    assert exit_code == 1
    assert any(
        rec.message
        in {
            "tools.gen_dummy_kb.vision_hardcheck.failed",
            "tools.gen_dummy_kb.vision_yaml_compile_failed",
        }
        for rec in caplog.records
    )
    assert any(rec.message == "tools.gen_dummy_kb.hardcheck.failed" for rec in caplog.records)


def test_logs_run_failed_on_out_of_workspace_pdf(caplog, tmp_path, monkeypatch):
    caplog.set_level("ERROR")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    _stub_minimal_environment(monkeypatch, tmp_path, run_vision_return=_boom)
    monkeypatch.setenv("VISION_MODE", "DEEP")
    # simuliamo un PDF che vive fuori dal workspace (trigger del Path traversal)
    monkeypatch.setattr(
        gen_dummy_mod,
        "_pdf_path",
        lambda slug: tmp_path / "VisionStatement.pdf",
    )
    args = ["--slug", "dummy", "--name", "Dummy", "--no-drive"]
    try:
        exit_code = gen_dummy_main(args)
    finally:
        clear_base_cache()
    assert exit_code == 1
    assert any(rec.message == "tools.gen_dummy_kb.run_failed" for rec in caplog.records)
