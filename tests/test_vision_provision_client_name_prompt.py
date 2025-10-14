from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF non disponibile: installa PyMuPDF/PyMuPDF wheels")

import src.semantic.vision_provision as vp


def test_provision_uses_client_name_in_prompt(dummy_workspace, dummy_ctx, dummy_logger, monkeypatch):
    slug = dummy_workspace["slug"]
    pdf = dummy_workspace["vision_pdf"]
    mapping_path = dummy_workspace["semantic_mapping"]
    cartelle_path = dummy_workspace["cartelle_raw"]
    ctx = dummy_ctx
    ctx.client_name = "ACME S.p.A."
    logger = dummy_logger

    seen: dict[str, str] = {}

    def _fake_vector_store(client, pdf_path):
        return "vs_dummy"

    monkeypatch.setattr(vp, "_create_vector_store_with_pdf", _fake_vector_store)
    monkeypatch.setattr(vp, "make_openai_client", lambda: object())

    def fake_call(
        client,
        *,
        engine,
        model,
        user_block,
        vs_id,
        snapshot_text,
        inline_sections,
        strict_output,
    ):  # type: ignore[no-untyped-def]
        seen["user_block"] = user_block
        return (
            {
                "context": {"slug": slug, "client_name": ctx.client_name},
                "areas": [
                    {"key": "core", "ambito": "A", "descrizione": "D", "keywords": []},
                ],
            },
            engine,
        )

    monkeypatch.setattr(vp, "_call_semantic_mapping_response", fake_call)

    original_mapping = mapping_path.read_text(encoding="utf-8")
    original_cartelle = cartelle_path.read_text(encoding="utf-8")

    try:
        out = vp.provision_from_vision(ctx, logger, slug=slug, pdf_path=pdf)
        out_mapping = Path(out["mapping"])
        out_cartelle = Path(out["cartelle_raw"])
        assert out_mapping == mapping_path
        assert out_cartelle == cartelle_path
        assert mapping_path.exists()
        assert cartelle_path.exists()
    finally:
        mapping_path.write_text(original_mapping, encoding="utf-8")
        cartelle_path.write_text(original_cartelle, encoding="utf-8")

    ub = seen.get("user_block", "")
    assert f"client_name: {ctx.client_name}" in ub
