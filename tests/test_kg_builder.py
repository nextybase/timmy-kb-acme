# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path

import pytest

import timmy_kb.cli.kg_builder as kg_builder
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from timmy_kb.cli.kg_builder import _load_raw_tags


def _create_minimal_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    config_payload = {
        "ops": {
            "log_level": "INFO",
        },
    }
    _write_json(workspace / "config" / "config.yaml", config_payload)
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


def _create_client_context(workspace: Path, slug: str = "dummy") -> ClientContext:
    return ClientContext.load(
        slug=slug,
        repo_root_dir=workspace,
        require_drive_env=False,
        bootstrap_config=False,
        run_id="kg-builder",
    )


def _write_tags_raw(semantic: Path, namespace: str = "dummy") -> None:
    payload = {
        "namespace": namespace,
        "tags": [
            {
                "raw_label": "alpha",
                "contexts": ["ctx"],
            }
        ],
    }
    _write_json(semantic / "tags_raw.json", payload)


def test_load_raw_tags_handles_list_structure(tmp_path: Path) -> None:
    workspace = _create_minimal_workspace(tmp_path)
    semantic = workspace / "semantic"
    payload = {
        "namespace": "dummy",
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

    result = _load_raw_tags(workspace, slug="dummy")

    assert result.namespace == "dummy"
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

    result = _load_raw_tags(workspace, slug="dummy")

    labels = {tag.raw_label for tag in result.tags}
    assert "raw/A" in labels
    assert "custom-label" in labels
    assert any("ctx-a" in ctx for tag in result.tags for ctx in tag.contexts)
    assert any("ctx-b" in ctx for tag in result.tags for ctx in tag.contexts)


@pytest.mark.parametrize("message", ("boom", "invalid json"))
def test_invoke_assistant_raises_on_error(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    def _raise(*_a, **_k):
        raise ConfigError(message)

    monkeypatch.setattr(kg_builder, "invoke_kgraph_messages", _raise)

    with pytest.raises(ConfigError):
        kg_builder._invoke_assistant([{"role": "user", "content": "hi"}], redact_logs=False)


def test_build_kg_for_workspace_creates_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _create_minimal_workspace(tmp_path)
    semantic = workspace / "semantic"
    _write_tags_raw(semantic, namespace="dummy")

    payload = {
        "schema_version": "kg-tags-0.1",
        "namespace": "dummy",
        "tags": [],
        "relations": [],
    }
    monkeypatch.setattr(kg_builder, "_invoke_assistant", lambda *args, **kwargs: payload)

    ctx = _create_client_context(workspace)
    kg = kg_builder.build_kg_for_workspace(ctx, namespace="dummy")

    json_path = semantic / "kg.tags.json"
    md_path = semantic / "kg.tags.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["namespace"] == "dummy"
    assert md_path.exists()
    assert md_path.read_text(encoding="utf-8").strip()
    assert kg.namespace == "dummy"


def test_build_kg_requires_tags_raw(tmp_path: Path) -> None:
    workspace = _create_minimal_workspace(tmp_path)
    ctx = _create_client_context(workspace)

    with pytest.raises(FileNotFoundError):
        kg_builder.build_kg_for_workspace(ctx, namespace="dummy")
