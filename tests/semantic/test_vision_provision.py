# tests/semantic/test_vision_provision.py
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

import semantic.vision_provision as vp
from pipeline.exceptions import ConfigError
from semantic.vision_provision import HaltError, provision_from_vision

pytestmark = pytest.mark.regression_light


class _Ctx:
    """Context minimale: base_dir, client_name e settings letti dal config loader in app."""

    def __init__(self, base_dir: Path, client_name: str = "Dummy Srl"):
        self.base_dir = base_dir
        self.client_name = client_name
        # SSoT: il nome dell'env da cui ricavare l'assistant_id
        self.settings = {"vision": {"assistant_id_env": "OBNEXT_ASSISTANT_ID"}}


def _fake_pdf_text() -> str:
    # Heading esatte (una per riga) come richieste dal parser
    return (
        "Vision\n"
        "La visione...\n"
        "Mission\n"
        "La missione...\n"
        "Goal\n"
        "Obiettivi...\n"
        "Framework etico\n"
        "Valori e policy...\n"
        "Prodotto/Azienda\n"
        "Descrizione del prodotto/azienda...\n"
        "Mercato\n"
        "Descrizione del mercato...\n"
    )


def _ok_payload(slug: str) -> dict:
    return {
        "version": "1.0-beta",
        "source": "vision",
        "status": "ok",
        "context": {"slug": slug, "client_name": "Dummy Srl"},
        "areas": [
            {
                "key": "governance",
                "ambito": "governance",
                "descrizione_breve": "Organi e decisioni; per tracciabilità e conformità.",
                "descrizione_dettagliata": {
                    "include": ["verbale CdA", "delibera", "statuto"],
                    "exclude": ["contratti"],
                    "artefatti_note": "Registro delibere per audit trail",
                },
                "documents": ["verbale CdA", "delibera", "statuto"],
                "artefatti": ["registro_delibere.md"],
                "correlazioni": {
                    "entities": [{"id": "cda", "label": "Consiglio di Amministrazione"}],
                    "relations": [{"subj": "delibera", "pred": "approvata_da", "obj": "cda", "card": "N:1"}],
                    "chunking_hints": ["Un verbale per chunk"],
                },
            },
            {
                "key": "it-data",
                "ambito": "it-data",
                "descrizione_breve": "Infrastrutture e dati; per resilienza e governance.",
                "descrizione_dettagliata": {
                    "include": ["architetture", "backup/DR"],
                    "exclude": [],
                    "artefatti_note": "",
                },
                "documents": ["architetture", "backup/DR"],
                "artefatti": ["playbook_incident.md"],
            },
            {
                "key": "prodotto-servizio",
                "ambito": "prodotto-servizio",
                "descrizione_breve": "Requisiti e manuali; per progettazione e rilascio.",
                "descrizione_dettagliata": {
                    "include": ["PRD", "roadmap"],
                    "exclude": ["contratti"],
                    "artefatti_note": "",
                },
                "documents": ["PRD", "roadmap", "manuale utente"],
                "artefatti": ["template_PRD.md"],
            },
        ],
        "system_folders": {
            "identity": {"documents": ["statuto", "visura camerale", "certificazioni"]},
            "glossario": {"artefatti": ["glossario.yaml"], "terms_hint": ["PRD", "SLA"]},
        },
        "metadata_policy": {
            "chunk_length_tokens": {"target": 800, "overlap": 100},
            "mandatory_fields": ["slug", "area_key", "ambito", "doc_class", "doc_uid", "chunk_id"],
        },
    }


def _halt_payload(slug: str) -> dict:
    return {
        "version": "1.0-beta",
        "source": "vision",
        "status": "halt",
        "context": {"slug": slug, "client_name": "Dummy Srl"},
        "missing": {
            "sections": ["Mission", "Framework etico"],
            "details": [
                {"section": "Mission", "reason": "mancano obiettivi misurabili"},
                {"section": "Framework etico", "reason": "assenza di policy sui dati"},
            ],
        },
        "message_ui": "Integra Mission e Framework etico e riprova.",
    }


@pytest.fixture(autouse=True)
def _no_retention(monkeypatch):
    # Evita side-effect della retention sui test
    monkeypatch.setattr(vp, "purge_old_artifacts", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _stub_openai_client(monkeypatch):
    """Evita dipendenze dirette dallo SDK OpenAI: restiamo su payload mockati."""

    class _DummyClient:
        pass

    monkeypatch.setattr(vp, "make_openai_client", lambda: _DummyClient())


def test_provision_ok_writes_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-srl"
    ctx = _Ctx(tmp_path)

    # crea file PDF vuoto (esistenza richiesta da ensure_within_and_resolve + checks)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")

    # env assistant id (il codice lo legge DOPO aver letto il nome var da ctx.settings)
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")

    # patch estrazione PDF e risposta assistant
    monkeypatch.setattr(vp, "_extract_pdf_text", lambda *a, **k: _fake_pdf_text())
    monkeypatch.setattr(vp, "_call_assistant_json", lambda **k: _ok_payload(slug))

    # run
    res = provision_from_vision(ctx, logger=logging.getLogger("test"), slug=slug, pdf_path=pdf)

    # assert file paths
    mapping = Path(res["mapping"])
    raw = Path(res["cartelle_raw"])
    assert mapping.is_file(), "semantic_mapping.yaml non scritto"
    assert raw.is_file(), "cartelle_raw.yaml non scritto"

    # contenuto semantic_mapping.yaml
    m = yaml.safe_load(mapping.read_text(encoding="utf-8"))
    assert m["source"] == "vision"
    assert m["context"]["slug"] == slug
    assert 3 <= len(m["areas"]) <= 9
    assert "system_folders" in m and "identity" in m["system_folders"] and "glossario" in m["system_folders"]
    # check documents/artefatti nella prima area
    a0 = m["areas"][0]
    assert "documents" in a0 and len(a0["documents"]) >= 1
    assert "artefatti" in a0

    # contenuto cartelle_raw.yaml
    r = yaml.safe_load(raw.read_text(encoding="utf-8"))
    assert r["source"] == "vision"
    keys = [f["key"] for f in r["folders"]]
    assert "identity" in keys and "glossario" in keys
    # examples derivano da documents/include
    gov = next(f for f in r["folders"] if f["key"] == "governance")
    assert len(gov["examples"]) >= 1


def test_provision_halt_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-srl"
    ctx = _Ctx(tmp_path)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")

    monkeypatch.setattr(vp, "_extract_pdf_text", lambda *a, **k: _fake_pdf_text())
    monkeypatch.setattr(vp, "_call_assistant_json", lambda **k: _halt_payload(slug))

    with pytest.raises(HaltError) as exc:
        provision_from_vision(ctx, logger=logging.getLogger("test"), slug=slug, pdf_path=pdf)
    assert "Integra Mission" in str(exc.value)

    # Nessun YAML deve essere scritto
    sem_dir = tmp_path / "semantic"
    assert not (sem_dir / "semantic_mapping.yaml").exists()
    assert not (sem_dir / "cartelle_raw.yaml").exists()


def test_provision_with_prepared_prompt_skips_pdf_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-srl"
    ctx = _Ctx(tmp_path)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")

    def _fail_extract(*_args: object, **_kwargs: object) -> None:
        pytest.fail("_extract_pdf_text non dovrebbe essere invocato quando prepared_prompt è fornito.")

    monkeypatch.setattr(vp, "_extract_pdf_text", _fail_extract)

    captured: dict[str, object] = {}

    def _fake_call(**kwargs: object) -> dict[str, object]:
        captured.update({k: v for k, v in kwargs.items() if k in {"user_messages", "strict_output"}})
        return _ok_payload(slug)

    monkeypatch.setattr(vp, "_call_assistant_json", _fake_call)

    prepared_prompt = "Prompt precompilato per il Vision Statement."

    res = provision_from_vision(
        ctx,
        logger=logging.getLogger("test"),
        slug=slug,
        pdf_path=pdf,
        prepared_prompt=prepared_prompt,
    )

    mapping = Path(res["mapping"])
    raw = Path(res["cartelle_raw"])
    assert mapping.exists() and raw.exists()

    user_messages = captured.get("user_messages")
    assert isinstance(user_messages, list) and user_messages, "user_messages non valorizzato."
    first_msg = user_messages[0]
    assert isinstance(first_msg, dict)
    assert first_msg.get("content") == prepared_prompt


def test_provision_uses_assistant_fallback_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-srl"
    ctx = _Ctx(tmp_path)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")

    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.setenv("ASSISTANT_ID", "asst_fallback")

    monkeypatch.setattr(vp, "_extract_pdf_text", lambda *a, **k: _fake_pdf_text())

    captured: dict[str, object] = {}

    def _fake_call(**kwargs: object) -> dict[str, object]:
        captured["assistant_id"] = kwargs.get("assistant_id")
        return _ok_payload(slug)

    monkeypatch.setattr(vp, "_call_assistant_json", _fake_call)

    res = provision_from_vision(ctx, logger=logging.getLogger("test"), slug=slug, pdf_path=pdf)

    assert Path(res["mapping"]).exists()
    assert Path(res["cartelle_raw"]).exists()
    assert captured.get("assistant_id") == "asst_fallback"


def test_provision_missing_assistant_id_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-srl"
    ctx = _Ctx(tmp_path)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")

    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.delenv("ASSISTANT_ID", raising=False)

    def _fail_extract(*_args: object, **_kwargs: object) -> None:  # pragma: no cover - should not be called
        raise AssertionError("_extract_pdf_text non dovrebbe essere invocato quando manca l'Assistant ID.")

    monkeypatch.setattr(vp, "_extract_pdf_text", _fail_extract)
    monkeypatch.setattr(
        vp,
        "_call_assistant_json",
        lambda **_k: pytest.fail("_call_assistant_json non dovrebbe essere raggiunto."),
    )

    with pytest.raises(ConfigError) as excinfo:
        provision_from_vision(ctx, logger=logging.getLogger("test"), slug=slug, pdf_path=pdf)

    assert "Assistant ID" in str(excinfo.value)
