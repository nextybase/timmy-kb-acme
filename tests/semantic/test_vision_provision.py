# SPDX-License-Identifier: GPL-3.0-only
# tests/semantic/test_vision_provision.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml  # type: ignore

import ai.vision_config as ai_config
import semantic.vision_provision as vp
from ai.types import AssistantConfig, ResponseJson
from ai.vision_config import resolve_vision_config, resolve_vision_retention_days
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings
from semantic.vision_provision import (
    CANONICAL_SECTIONS,
    HaltError,
    SectionStatus,
    _parse_required_sections,
    analyze_vision_sections,
)

pytestmark = pytest.mark.regression_light


class _Ctx:
    """Context minimale: base_dir, client_name e settings letti dal config loader in app."""

    def __init__(self, base_dir: Path, client_name: str = "Dummy Srl"):
        self.base_dir = base_dir
        self.client_name = client_name
        # SSoT: il nome dell'env da cui ricavare l'assistant_id
        self.settings = {"ai": {"vision": {"assistant_id_env": "OBNEXT_ASSISTANT_ID"}}}


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
        "Contesto Operativo\n"
        "Descrizione del contesto operativo...\n"
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


def _make_settings(use_kb: bool) -> Settings:
    return Settings(
        config_path=Path("config.yaml"),
        data={
            "openai": {},
            "ai": {
                "vision": {
                    "model": "gpt-4o-mini",
                    "assistant_id_env": "OBNEXT_ASSISTANT_ID",
                    "snapshot_retention_days": 30,
                    "strict_output": True,
                    "use_kb": use_kb,
                }
            },
            "ui": {},
            "retriever": {"throttle": {}},
            "ops": {},
        },
    )


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
    config = resolve_vision_config(ctx, override_model="test-model")
    retention_days = resolve_vision_retention_days(ctx)
    res = vp.provision_from_vision_with_config(
        ctx,
        logger=logging.getLogger("test"),
        slug=slug,
        pdf_path=pdf,
        config=config,
        retention_days=retention_days,
    )

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


def test_provision_ignores_engine_in_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-engine"
    ctx = _Ctx(tmp_path)
    ctx.settings["ai"]["vision"]["engine"] = "responses"

    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")

    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")
    monkeypatch.setattr(vp, "_extract_pdf_text", lambda *a, **k: _fake_pdf_text())

    captured: Dict[str, Any] = {}

    def _fake_call(**kwargs: Any) -> Dict[str, Any]:
        captured.update(kwargs)
        return _ok_payload(slug)

    monkeypatch.setattr(vp, "_call_assistant_json", _fake_call)

    config = resolve_vision_config(ctx, override_model="test-model")
    retention_days = resolve_vision_retention_days(ctx)
    vp.provision_from_vision_with_config(
        ctx=ctx,
        logger=logging.getLogger("test"),
        slug=slug,
        pdf_path=pdf,
        config=config,
        retention_days=retention_days,
    )

    assert "engine" not in captured


def test_provision_retention_fallback_on_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-retention"
    ctx = _Ctx(tmp_path)
    ctx.settings["ai"]["vision"]["snapshot_retention_days"] = 0

    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")

    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")
    monkeypatch.setattr(vp, "_extract_pdf_text", lambda *a, **k: _fake_pdf_text())
    monkeypatch.setattr(vp, "_call_assistant_json", lambda **_k: _ok_payload(slug))

    captured: Dict[str, Any] = {}

    def _fake_persist(prepared: Any, payload: Dict[str, Any], logger: Any, *, retention_days: int) -> Dict[str, Any]:
        captured["retention_days"] = retention_days
        return {
            "mapping": str(prepared.paths.mapping_yaml),
            "cartelle_raw": str(prepared.paths.cartelle_yaml),
        }

    monkeypatch.setattr(vp, "_persist_outputs", _fake_persist)

    config = resolve_vision_config(ctx, override_model="test-model")
    retention_days = resolve_vision_retention_days(ctx)
    vp.provision_from_vision_with_config(
        ctx=ctx,
        logger=logging.getLogger("test"),
        slug=slug,
        pdf_path=pdf,
        config=config,
        retention_days=retention_days,
    )

    assert captured.get("retention_days") == 30


def test_provision_halt_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-srl"
    ctx = _Ctx(tmp_path)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")

    monkeypatch.setattr(vp, "_extract_pdf_text", lambda *a, **k: _fake_pdf_text())
    monkeypatch.setattr(vp, "_call_assistant_json", lambda **k: _halt_payload(slug))

    config = resolve_vision_config(ctx, override_model="test-model")
    retention_days = resolve_vision_retention_days(ctx)
    with pytest.raises(HaltError) as exc:
        vp.provision_from_vision_with_config(
            ctx=ctx,
            logger=logging.getLogger("test"),
            slug=slug,
            pdf_path=pdf,
            config=config,
            retention_days=retention_days,
        )
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

    config = resolve_vision_config(ctx, override_model="test-model")
    retention_days = resolve_vision_retention_days(ctx)
    res = vp.provision_from_vision_with_config(
        ctx=ctx,
        logger=logging.getLogger("test"),
        slug=slug,
        pdf_path=pdf,
        config=config,
        retention_days=retention_days,
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
    ctx = _Ctx(tmp_path)
    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.setenv("ASSISTANT_ID", "asst_fallback")
    with pytest.raises(ConfigError) as excinfo:
        resolve_vision_config(ctx, override_model="test-model")
    assert "OBNEXT_ASSISTANT_ID" in str(excinfo.value)


def test_provision_missing_assistant_id_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _Ctx(tmp_path)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")

    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.delenv("ASSISTANT_ID", raising=False)

    with pytest.raises(ConfigError) as excinfo:
        resolve_vision_config(ctx, override_model="test-model")

    assert "Assistant ID" in str(excinfo.value)


def test_provision_with_config_skips_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "config-only"
    ctx = _Ctx(tmp_path)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")

    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.delenv("ASSISTANT_ID", raising=False)

    monkeypatch.setattr(vp, "_extract_pdf_text", lambda *a, **k: _fake_pdf_text())

    captured: Dict[str, object] = {}

    def _fake_call(**kwargs: object) -> dict[str, object]:
        captured["assistant_id"] = kwargs.get("assistant_id")
        return _ok_payload(slug)

    monkeypatch.setattr(vp, "_call_assistant_json", _fake_call)

    config = AssistantConfig(
        model="test-model",
        assistant_id="config-asst",
        assistant_env="OBNEXT_ASSISTANT_ID",
        use_kb=True,
        strict_output=True,
    )

    res = vp.provision_from_vision_with_config(
        ctx,
        logger=logging.getLogger("test"),
        slug=slug,
        pdf_path=pdf,
        config=config,
        retention_days=0,
    )

    assert Path(res["mapping"]).exists()
    assert Path(res["cartelle_raw"]).exists()
    assert captured.get("assistant_id") == "config-asst"


def test_semantic_with_config_does_not_reresolve_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "config-only"
    ctx = _Ctx(tmp_path)
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")

    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "config-asst")
    monkeypatch.setattr(vp, "_extract_pdf_text", lambda *a, **k: _fake_pdf_text())
    monkeypatch.setattr(vp, "_call_assistant_json", lambda **_: _ok_payload(slug))

    monkeypatch.setattr(
        ai_config, "resolve_vision_config", lambda *a, **k: pytest.fail("Semantic should not resolve config")
    )
    monkeypatch.setattr(
        "ai.vision_config.resolve_vision_retention_days",
        lambda *a, **k: pytest.fail("Semantic should not resolve retention"),
    )

    config = AssistantConfig(
        model="test-model",
        assistant_id="config-asst",
        assistant_env="OBNEXT_ASSISTANT_ID",
        use_kb=True,
        strict_output=True,
    )

    res = vp.provision_from_vision_with_config(
        ctx,
        logger=logging.getLogger("test"),
        slug=slug,
        pdf_path=pdf,
        config=config,
        retention_days=0,
    )

    assert Path(res["mapping"]).exists()
    assert Path(res["cartelle_raw"]).exists()


def test_analyze_sections_happy_path():
    reports = analyze_vision_sections(_fake_pdf_text())
    assert all(r.status == SectionStatus.PRESENT for r in reports)
    assert {r.name for r in reports} == set(vp.CANONICAL_SECTIONS)


def test_parse_required_sections_missing_raises():
    text = _fake_pdf_text().replace("Mission\nLa missione...\n", "")
    with pytest.raises(ConfigError) as excinfo:
        _parse_required_sections(text)
    assert "sezioni mancanti" in str(excinfo.value)


def test_parse_required_sections_empty_raises():
    text = _fake_pdf_text().replace("Goal\nObiettivi...\n", "Goal\n   \n")
    with pytest.raises(ConfigError) as excinfo:
        _parse_required_sections(text)
    assert "sezioni vuote" in str(excinfo.value)


def test_load_vision_yaml_requires_full_text(tmp_path: Path):
    yaml_path = tmp_path / "visionstatement.yaml"
    yaml_path.write_text(
        "version: 1\ncontent:\n  pages:\n    - Solo pagina senza full_text\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as excinfo:
        vp._load_vision_yaml_text(tmp_path, yaml_path, slug="demo")

    assert "full_text" in str(excinfo.value)


def test_analyze_vision_sections_realistic_text():
    text = (
        "Vision Statement di NeXT\n"
        "Vision\n"
        "NeXT si configura come un sistema adattivo di Intelligenza Artificiale.\n"
        "\n"
        "Mission\n"
        "La missione di NeXT è supportare imprese e territori con AI human-in-the-loop.\n"
        "\n"
        "Framework Etico\n"
        "Principi etici fittizi: trasparenza, supervisione umana, gestione sicura dei dati.\n"
        "\n"
        "Goal\n"
        "Obiettivi strutturati secondo logica temporale (Basket 3/6/12).\n"
        "\n"
        "Contesto Operativo\n"
        "Ambito settoriale: trasformazione digitale e organizzativa.\n"
    )
    reports = analyze_vision_sections(text)
    status_by_name = {r.name: r.status for r in reports}
    assert all(status_by_name[name] == SectionStatus.PRESENT for name in CANONICAL_SECTIONS)


def test_prepare_payload_sets_instructions_by_use_kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slug = "dummy-instructions"
    pdf = tmp_path / "vision.pdf"
    pdf.write_bytes(b"%PDF-FAKE%")
    ctx = _Ctx(tmp_path)
    ctx.settings["ai"]["vision"]["model"] = "gpt-4o-mini"

    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")

    config_true = AssistantConfig(
        model="gpt-4o-mini",
        assistant_id="asst_dummy",
        assistant_env="OBNEXT_ASSISTANT_ID",
        use_kb=True,
        strict_output=True,
    )
    prepared_true = vp._prepare_payload(
        ctx,
        slug,
        pdf,
        prepared_prompt="prompt",
        config=config_true,
        logger=logging.getLogger("test"),
        retention_days=0,
    )
    assert prepared_true.use_kb is True
    assert "File Search" in prepared_true.run_instructions
    assert "output finale deve SEMPRE" in prepared_true.run_instructions

    config_false = AssistantConfig(
        model="gpt-4o-mini",
        assistant_id="asst_dummy",
        assistant_env="OBNEXT_ASSISTANT_ID",
        use_kb=False,
        strict_output=True,
    )
    prepared_false = vp._prepare_payload(
        ctx,
        slug,
        pdf,
        prepared_prompt="prompt",
        config=config_false,
        logger=logging.getLogger("test"),
        retention_days=0,
    )
    assert prepared_false.use_kb is False
    assert "IGNORARE File Search" in prepared_false.run_instructions
    assert "usa esclusivamente il blocco Vision" in prepared_false.run_instructions


def test_invoke_assistant_passes_use_kb(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    captured: Dict[str, Any] = {}

    def _fake_call(**kwargs: Any) -> Dict[str, Any]:
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(vp, "_call_assistant_json", _fake_call)

    paths = vp._Paths(
        base_dir=tmp_path, semantic_dir=tmp_path, mapping_yaml=tmp_path / "a", cartelle_yaml=tmp_path / "b"
    )
    prepared = vp._VisionPrepared(
        slug="s",
        display_name="d",
        safe_pdf=tmp_path / "vision.pdf",
        prompt_text="p",
        model="gpt-4o-mini",
        assistant_id="asst",
        run_instructions="instr",
        use_kb=False,
        strict_output=True,
        client=object(),
        paths=paths,
        retention_days=0,
    )

    vp._invoke_assistant(prepared)

    assert captured.get("use_kb") is False
    assert captured.get("run_instructions") == "instr"


def test_call_assistant_json_skips_response_format_when_not_structured(monkeypatch: pytest.MonkeyPatch):
    captured: Dict[str, Any] = {}

    class _DummyClient:
        pass

    monkeypatch.setattr(
        vp,
        "_determine_structured_output",
        lambda client, assistant_id, strict_output: False,
    )

    def _fake_responses_api(**kwargs: Any) -> Dict[str, Any]:
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(vp, "_call_responses_json", _fake_responses_api)

    vp._call_assistant_json(
        client=_DummyClient(),
        assistant_id="asst",
        model="gpt-4o-mini",
        user_messages=[{"role": "user", "content": "hi"}],
        strict_output=False,
        run_instructions=None,
        use_kb=False,
    )

    assert captured.get("use_structured") is False
    assert captured.get("response_format") == {"type": "json_object"}


def test_call_assistant_json_uses_schema_when_strict(monkeypatch: pytest.MonkeyPatch):
    captured: Dict[str, Any] = {}

    class _DummyClient:
        pass

    # Usa la logica reale: strict_output True forza schema
    monkeypatch.setattr(
        vp,
        "_call_responses_json",
        lambda **kwargs: captured.update(kwargs) or {},
    )

    vp._call_assistant_json(
        client=_DummyClient(),
        assistant_id="asst",
        model="gpt-4o-mini",
        user_messages=[{"role": "user", "content": "hi"}],
        strict_output=True,
        run_instructions=None,
        use_kb=True,
    )

    rf = captured.get("response_format")
    assert isinstance(rf, dict)
    assert rf.get("type") == "json_schema"


def test_call_responses_json_errors_on_exception(monkeypatch: pytest.MonkeyPatch):
    def _raise(**_: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(vp, "run_json_model", _raise)

    with pytest.raises(ConfigError):
        vp._call_responses_json(
            client=object(),
            assistant_id="asst",
            model="gpt-4o-mini",
            user_messages=[{"role": "user", "content": "hi"}],
            run_instructions=None,
            use_kb=False,
            use_structured=True,
            response_format={"type": "json_object"},
        )


def test_call_responses_json_uses_model_not_assistant_id(monkeypatch: pytest.MonkeyPatch):
    captured: Dict[str, Any] = {}

    def _fake_run_json_model(**kwargs: Any) -> ResponseJson:
        captured.update(kwargs)
        return ResponseJson(model=kwargs.get("model", ""), data={}, raw_text="{}", raw={})

    monkeypatch.setattr(vp, "run_json_model", _fake_run_json_model)

    vp._call_responses_json(
        client=object(),
        assistant_id="asst",
        model="gpt-4o-mini",
        user_messages=[{"role": "user", "content": "hi"}],
        run_instructions=None,
        use_kb=False,
        use_structured=True,
        response_format={"type": "json_object"},
    )

    assert captured.get("model") == "gpt-4o-mini"
    assert captured.get("metadata", {}).get("assistant_id") == "asst"


def test_load_vision_schema_fills_required_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schema_path = tmp_path / "VisionOutput.schema.json"
    schema_payload = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
    }
    schema_path.write_text(json.dumps(schema_payload), encoding="utf-8")

    vp._load_vision_schema.cache_clear()
    vp._vision_schema_path.cache_clear()
    monkeypatch.setattr(vp, "_vision_schema_path", lambda: schema_path)

    loaded = vp._load_vision_schema()
    assert loaded.get("required") is None


def test_load_vision_schema_filters_required_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schema_path = tmp_path / "VisionOutput.schema.json"
    schema_payload = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["a", "c"],
    }
    schema_path.write_text(json.dumps(schema_payload), encoding="utf-8")

    vp._load_vision_schema.cache_clear()
    vp._vision_schema_path.cache_clear()
    monkeypatch.setattr(vp, "_vision_schema_path", lambda: schema_path)

    loaded = vp._load_vision_schema()
    assert loaded["required"] == ["a", "c"]
