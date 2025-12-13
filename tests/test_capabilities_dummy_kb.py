# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline.capabilities.dummy_kb import DriveBindings, DummyHelpers, load_dummy_drive_helpers, load_dummy_helpers


def _make_module(**attrs):
    return SimpleNamespace(**attrs)


def test_load_dummy_helpers_success(monkeypatch):
    modules = {
        "src.tools.dummy.bootstrap": _make_module(client_base=lambda: "base", pdf_path=lambda: "pdf"),
        "src.tools.dummy.orchestrator": _make_module(
            build_dummy_payload=lambda: "payload",
            register_client=lambda: "register",
            validate_dummy_structure=lambda: "validate",
        ),
        "src.tools.dummy.semantic": _make_module(
            ensure_book_skeleton=lambda: "skeleton",
            ensure_local_readmes=lambda: "readmes",
            ensure_minimal_tags_db=lambda: "tags",
            ensure_raw_pdfs=lambda: "raw",
            load_mapping_categories=lambda: "mapping",
            write_basic_semantic_yaml=lambda: "yaml",
        ),
        "src.tools.dummy.vision": _make_module(run_vision_with_timeout=lambda: "vision"),
    }

    def fake_import(name: str):
        return modules[name]

    monkeypatch.setattr("pipeline.capabilities.dummy_kb.import_module", fake_import)

    helpers = load_dummy_helpers()
    assert isinstance(helpers, DummyHelpers)
    assert helpers.build_dummy_payload() == "payload"


def test_load_dummy_helpers_missing(monkeypatch):
    def failing_import(name: str):
        raise ImportError("not found")

    monkeypatch.setattr("pipeline.capabilities.dummy_kb.import_module", failing_import)
    with pytest.raises(ImportError) as excinfo:
        load_dummy_helpers()
    assert "Impossibile importare" in str(excinfo.value)


def test_load_dummy_drive_helpers(monkeypatch):
    expected = _make_module(
        call_drive_build_from_mapping=lambda: "build",
        call_drive_emit_readmes=lambda: "emit",
        call_drive_min=lambda: "min",
    )

    monkeypatch.setattr(
        "pipeline.capabilities.dummy_kb.import_module", lambda name: expected if name.endswith("drive") else None
    )
    bindings = load_dummy_drive_helpers()
    assert isinstance(bindings, DriveBindings)
    assert bindings.call_drive_min() == "min"
