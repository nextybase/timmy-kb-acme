# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
KG_BUILDER_PATH = ROOT / "src" / "timmykb" / "kg_builder.py"
_KG_MODELS_PATH = ROOT / "src" / "timmykb" / "kg_models.py"
_KG_MODELS_SPEC = importlib.util.spec_from_file_location("timmykb.kg_models", _KG_MODELS_PATH)
if _KG_MODELS_SPEC is None or _KG_MODELS_SPEC.loader is None:
    raise RuntimeError("Impossibile caricare kg_models per i test.")
kg_models = importlib.util.module_from_spec(_KG_MODELS_SPEC)
sys.modules["timmykb.kg_models"] = kg_models
_KG_MODELS_SPEC.loader.exec_module(kg_models)

_KG_SPEC = importlib.util.spec_from_file_location("timmykb.kg_builder", KG_BUILDER_PATH)
if _KG_SPEC is None or _KG_SPEC.loader is None:
    raise RuntimeError("Impossibile caricare kg_builder per i test.")
kg_builder = importlib.util.module_from_spec(_KG_SPEC)
sys.modules["timmykb.kg_builder"] = kg_builder
_KG_SPEC.loader.exec_module(kg_builder)

RawTag = kg_builder.RawTag
TagKgInput = kg_builder.TagKgInput
_load_raw_tags = kg_builder._load_raw_tags
call_openai_tag_kg_assistant = kg_builder.call_openai_tag_kg_assistant


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_raw_tags_handles_list_structure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    semantic = workspace / "semantic"
    semantic.mkdir(parents=True)
    payload = {
        "namespace": "acme-labs",
        "tags": [
            {
                "raw_label": "alpha",
                "contexts": ["ctx-1", "ctx-2"],
                "relative_path": "raw/doc.pdf",
            }
        ],
    }
    _write_json(semantic / "tags_raw.json", payload)
    context_file = semantic / "tags_context.jsonl"
    context_file.write_text('{"context": "value"}\n', encoding="utf-8")

    result = _load_raw_tags(workspace)

    assert result.namespace == "acme-labs"
    assert result.contexts_file.endswith("tags_context.jsonl")
    assert len(result.tags) == 1
    assert "ctx-1" in result.tags[0].contexts


def test_load_raw_tags_handles_dict_structure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    semantic = workspace / "semantic"
    semantic.mkdir(parents=True)
    payload = {
        "tags": {
            "raw/A": {
                "contexts": ["ctx-a"],
                "sources": {"path": ["raw/A"]},
            },
            "raw/B": [
                {"label": "custom-label", "contexts": ["ctx-b"]},
            ],
        }
    }
    _write_json(semantic / "tags_raw.json", payload)

    result = _load_raw_tags(workspace)

    labels = {tag.raw_label for tag in result.tags}
    assert "raw/A" in labels
    assert "custom-label" in labels
    assert any("ctx-a" in ctx for tag in result.tags for ctx in tag.contexts)
    assert any("ctx-b" in ctx for tag in result.tags for ctx in tag.contexts)


def test_call_openai_tag_kg_assistant_parses_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = TagKgInput(
        namespace="demo",
        tags_file="tags.json",
        contexts_file=None,
        tags=[RawTag(raw_label="alpha", contexts=["ctx"])],
    )

    tool_output = {
        "schema_version": "kg-tags-0.1",
        "namespace": "demo",
        "tags": [
            {
                "id": "tag:alpha",
                "label": "Alpha",
                "description": "Example",
                "category": "area",
                "status": "active",
                "language": "it",
                "aliases": [],
                "examples": [],
            }
        ],
        "relations": [],
    }

    tool_function = SimpleNamespace(name="build_tag_kg", arguments=json.dumps(tool_output, ensure_ascii=False))
    tool_call = SimpleNamespace(function=tool_function)
    step_details = SimpleNamespace(type="tool_calls", tool_calls=[tool_call])
    step = SimpleNamespace(step_details=step_details)

    class DummyMessages:
        def create(self, **kwargs: object) -> None:
            self.last = kwargs

    class DummySteps:
        def list(self, *args: object, **kwargs: object) -> list[SimpleNamespace]:
            return [step]

    class DummyRuns:
        def __init__(self) -> None:
            self.steps = DummySteps()

        def create_and_poll(self, *args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(status="completed", id="run", thread_id="thread")

    class DummyThreads:
        def __init__(self) -> None:
            self.messages = DummyMessages()
            self.runs = DummyRuns()

        def create(self) -> SimpleNamespace:
            return SimpleNamespace(id="thread")

    class DummyBeta:
        def __init__(self) -> None:
            self.threads = DummyThreads()

    class DummyClient:
        def __init__(self) -> None:
            self.beta = DummyBeta()

    monkeypatch.setattr(kg_builder, "make_openai_client", lambda: DummyClient())

    def _fake_get_env_var(name, default=None, **kwargs):
        return "tag-kg" if name == "TAG_KG_BUILDER_ASSISTANT_ID" else default

    monkeypatch.setattr(kg_builder, "get_env_var", _fake_get_env_var)

    kg = call_openai_tag_kg_assistant(payload)

    assert kg.namespace == "demo"
    assert len(kg.tags) == 1
    assert kg.tags[0].id == "tag:alpha"
