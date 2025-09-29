import logging
from pathlib import Path
from types import SimpleNamespace

import src.semantic.vision_provision as vp


def test_provision_uses_client_name_in_prompt(tmp_path, monkeypatch):
    base = tmp_path / "ws"
    base.mkdir()
    pdf = base / "config" / "VisionStatement.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4\n%dummy\n")

    # Context con client_name reale
    ctx = SimpleNamespace(base_dir=base, client_name="ACME S.p.A.")
    logger = logging.getLogger("test.vision")

    seen = {}

    # Evita rete/SDK reali
    monkeypatch.setattr(vp, "_create_vector_store_with_pdf", lambda client, pdf_path: "vs_dummy")
    monkeypatch.setattr(vp, "make_openai_client", lambda: object())

    def fake_call(client, *, model, user_block, vs_id, snapshot_text):  # type: ignore[no-untyped-def]
        seen["user_block"] = user_block
        # Payload minimo valido per la validazione + conversione YAML
        return {
            "context": {"slug": "x", "client_name": ctx.client_name},
            "areas": [
                {"key": "core", "ambito": "A", "descrizione": "D", "esempio": []},
            ],
        }

    monkeypatch.setattr(vp, "_call_semantic_mapping_response", fake_call)

    out = vp.provision_from_vision(ctx, logger, slug="x", pdf_path=pdf)
    assert Path(out["mapping"]).exists()
    assert Path(out["cartelle_raw"]).exists()

    # Il prompt deve includere il client_name reale
    ub = seen.get("user_block", "")
    assert f"client_name: {ctx.client_name}" in ub
