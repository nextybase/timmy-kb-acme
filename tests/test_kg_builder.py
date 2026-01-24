# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path

import pytest

import timmy_kb.cli.kg_builder as kg_builder
from pipeline.exceptions import ConfigError
from timmy_kb.cli.kg_builder import RawTag, TagKgInput, _load_raw_tags, call_openai_tag_kg_assistant


def _create_minimal_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    (workspace / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    (workspace / "book").mkdir(parents=True, exist_ok=True)
    (workspace / "book" / "README.md").write_text("# README", encoding="utf-8")
    (workspace / "book" / "SUMMARY.md").write_text("# SUMMARY", encoding="utf-8")
    (workspace / "semantic").mkdir(parents=True, exist_ok=True)
    (workspace / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "normalized").mkdir(parents=True, exist_ok=True)
    (workspace / "logs").mkdir(parents=True, exist_ok=True)
    return workspace


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_raw_tags_handles_list_structure(tmp_path: Path) -> None:
    workspace = _create_minimal_workspace(tmp_path)
    semantic = workspace / "semantic"
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
    workspace = _create_minimal_workspace(tmp_path)
    semantic = workspace / "semantic"
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

    monkeypatch.setattr(kg_builder, "invoke_kgraph_messages", lambda *a, **k: tool_output)

    kg = call_openai_tag_kg_assistant(payload)

    assert kg.namespace == "demo"
    assert len(kg.tags) == 1
    assert kg.tags[0].id == "tag:alpha"


def test_invoke_assistant_raises_on_responses_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_a, **_k):
        raise ConfigError("boom")

    monkeypatch.setattr(kg_builder, "invoke_kgraph_messages", _raise)

    with pytest.raises(ConfigError):
        kg_builder._invoke_assistant([{"role": "user", "content": "hi"}], redact_logs=False)


def test_invoke_assistant_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_a, **_k):
        raise ConfigError("invalid json")

    monkeypatch.setattr(kg_builder, "invoke_kgraph_messages", _raise)

    with pytest.raises(ConfigError):
        kg_builder._invoke_assistant([{"role": "user", "content": "hi"}], redact_logs=False)


def test_resolve_kgraph_model_from_settings_object() -> None:
    model = kg_builder._resolve_kgraph_model(settings={"ai": {"kgraph": {"model": "gpt-4.1"}}})
    assert model == "gpt-4.1"
