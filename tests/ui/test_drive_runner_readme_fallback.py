# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations


def test_render_readme_payload_fallback_on_missing_reportlab(monkeypatch):
    import ui.services.drive_runner as dr

    def _raise_import_error(*_args, **_kwargs):
        raise ImportError("reportlab missing")

    monkeypatch.setattr(dr, "_render_readme_pdf_bytes", _raise_import_error)

    data, mime, service_only, reason = dr._render_readme_payload(
        title="Test README",
        descr="Descrizione",
        examples=["a", "b"],
    )

    assert mime == "text/plain"
    assert service_only is True
    assert reason == "capability_missing:reportlab"
    assert b"README - Test README" in data


def test_service_only_drive_properties_reason_default():
    import ui.services.drive_runner as dr

    props = dr._service_only_drive_properties(None)

    assert props["SERVICE_ONLY"] == "true"
    assert props["service_only"] == "true"
    assert props["service_reason"] == "unknown"


def test_service_only_core_folder_blocked():
    import ui.services.drive_runner as dr

    try:
        dr._assert_service_only_not_core_folder("book")
    except RuntimeError as exc:
        assert "SERVICE_ONLY" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for core folder")


def test_reportlab_missing_blocks_core_folder(monkeypatch):
    import ui.services.drive_runner as dr

    def _raise_import_error(*_args, **_kwargs):
        raise ImportError("reportlab missing")

    monkeypatch.setattr(dr, "_render_readme_pdf_bytes", _raise_import_error)

    _data, _mime, service_only, _reason = dr._render_readme_payload(
        title="Core README",
        descr="",
        examples=[],
    )
    assert service_only is True
    try:
        dr._assert_service_only_not_core_folder("book")
    except RuntimeError:
        assert True
    else:
        raise AssertionError("Expected RuntimeError for core folder when service_only")
