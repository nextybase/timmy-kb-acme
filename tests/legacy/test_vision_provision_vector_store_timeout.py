from types import SimpleNamespace

import pytest

import src.semantic.vision_provision as vp
from pipeline.exceptions import ConfigError


def test_vector_store_timeout_raises_configerror(dummy_workspace, monkeypatch):
    tmp_dir = dummy_workspace["base"] / "tmp" / "vector_store_timeout"
    pdf = tmp_dir / "config" / "VisionStatement.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4\n%dummy\n")

    # Monkeypatch vector store ops to never reach completed >= 1
    def fake_ops(_client):  # type: ignore[no-untyped-def]
        def create_vs(**kwargs):  # type: ignore[no-untyped-def]
            return {"id": "vs-timeout"}

        def retrieve_vs(_vs_id):  # type: ignore[no-untyped-def]
            return SimpleNamespace(file_counts=SimpleNamespace(completed=0))

        def add_file(_vs_id, _pdf, _fid):  # type: ignore[no-untyped-def]
            return None

        return create_vs, retrieve_vs, add_file, "upload"

    monkeypatch.setattr(vp, "_resolve_vector_store_ops", fake_ops)
    monkeypatch.setattr(vp.time, "sleep", lambda *a, **k: None)

    with pytest.raises(ConfigError) as exc:
        vp._create_vector_store_with_pdf(object(), pdf)

    # Messaggio include almeno il nome file (path completo non garantito nella __str__ di ConfigError)
    assert pdf.name in str(exc.value)
