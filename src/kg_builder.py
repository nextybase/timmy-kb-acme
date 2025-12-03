# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from ai.client_factory import make_openai_client
from kg_models import TagKnowledgeGraph
from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

logger = get_structured_logger("kg_builder")


@dataclass
class RawTag:
    raw_label: str
    contexts: List[str]


@dataclass
class TagKgInput:
    namespace: str
    tags_file: str
    contexts_file: Optional[str]
    tags: List[RawTag]

    def to_messages(self) -> list[dict[str, Any]]:
        content = [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "namespace": self.namespace,
                        "tags_file": self.tags_file,
                        "contexts_file": self.contexts_file,
                        "tags": [
                            {
                                "raw_label": t.raw_label,
                                "contexts": t.contexts,
                            }
                            for t in self.tags
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        return [{"role": "user", "content": content}]


def _iter_entries(source: Any, default_label: str | None = None) -> Iterable[dict[str, Any]]:
    if source is None:
        return []
    if isinstance(source, list):
        for val in source:
            yield from _iter_entries(val, default_label=default_label)
        return []
    if isinstance(source, Mapping):
        is_tag_entry = any(k in source for k in ("raw_label", "label", "contexts", "relative_path", "path"))
        if is_tag_entry:
            entry = dict(source)
            if default_label and not entry.get("raw_label") and not entry.get("label"):
                entry["raw_label"] = default_label
            yield entry
            return []
        for key, val in source.items():
            yield from _iter_entries(val, default_label=key or default_label)
        return []
    return []


def _load_tags_raw(raw_path: Path, default_namespace: str) -> tuple[list[RawTag], str]:
    raw_payload = read_text_safe(raw_path.parent, raw_path, encoding="utf-8")
    raw_data = json.loads(raw_payload)
    tag_source = raw_data.get("tags") if isinstance(raw_data, Mapping) else raw_data
    namespace = raw_data.get("namespace", default_namespace) if isinstance(raw_data, Mapping) else default_namespace
    tags_raw: list[RawTag] = []
    for entry in _iter_entries(tag_source):
        raw_label = entry.get("raw_label") or entry.get("label")
        if not raw_label:
            continue
        contexts = entry.get("contexts") or []
        meta_ctx = entry.get("relative_path") or entry.get("path")
        if meta_ctx:
            contexts = list(contexts) + [f"relative_path: {meta_ctx}"]
        tags_raw.append(RawTag(raw_label=str(raw_label), contexts=[str(c) for c in contexts]))
    if not tags_raw:
        raise ConfigError("Il file tags_raw.json non contiene tag validi", file_path=str(raw_path))
    return tags_raw, str(namespace)


def _maybe_load_contexts(contexts_path: Optional[Path]) -> Optional[str]:
    if contexts_path is None:
        return None
    return read_text_safe(contexts_path.parent, contexts_path, encoding="utf-8")


def _prepare_input(namespace: str, semantic_dir: Path) -> TagKgInput:
    tags_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_raw.json")
    contexts_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_context.jsonl")
    tags_raw, resolved_namespace = _load_tags_raw(tags_path, namespace)
    return TagKgInput(
        namespace=resolved_namespace,
        tags_file=str(tags_path),
        contexts_file=str(contexts_path) if contexts_path is not None else None,
        tags=tags_raw,
    )


def _load_raw_tags(workspace_root: Path) -> TagKgInput:
    workspace_root = workspace_root.resolve()
    semantic_dir = ensure_within_and_resolve(workspace_root, workspace_root / "semantic")
    return _prepare_input(workspace_root.name, semantic_dir)


def _invoke_assistant(messages: list[dict[str, Any]], *, redact_logs: bool) -> dict[str, Any]:
    assistant_id = get_env_var("TAG_KG_BUILDER_ASSISTANT_ID", required=True)
    client = make_openai_client()
    completion = client.chat.completions.create(
        model=assistant_id,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    first_choice = completion.choices[0].message.content or "{}"
    return json.loads(first_choice)


def call_openai_tag_kg_assistant(payload: TagKgInput, *, redact_logs: bool = False) -> TagKnowledgeGraph:
    raw_output = _invoke_assistant(payload.to_messages(), redact_logs=redact_logs)
    kg = TagKnowledgeGraph.from_dict(raw_output)
    kg.namespace = payload.namespace
    return kg


def _save_outputs(semantic_dir: Path, kg: TagKnowledgeGraph) -> dict[str, str]:
    kg_json_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.json")
    kg_md_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.md")

    semantic_dir.mkdir(parents=True, exist_ok=True)
    safe_write_text(kg_json_path, json.dumps(kg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8", atomic=True)

    def _render_md(graph: TagKnowledgeGraph) -> str:
        lines = [
            f"# Knowledge Graph dei tag (namespace: {graph.namespace})",
            "",
            f"Schema version: {graph.schema_version}",
            f"Generato da: {graph.generated_by or 'assistant'}",
            f"Generato il: {graph.generated_at or ''}",
            "",
            "## Tag",
        ]
        for tag in graph.tags:
            lines.append(f"- **{tag.label}** (id: {tag.id}, categoria: {tag.category}, stato: {tag.status})")
            if tag.aliases:
                lines.append(f"  - Aliases: {', '.join(tag.aliases)}")
            if tag.examples:
                lines.append(f"  - Esempi: {', '.join(tag.examples)}")
            if tag.extra:
                lines.append(f"  - Extra: {json.dumps(tag.extra, ensure_ascii=False)}")
        lines.append("")
        lines.append("## Relazioni")
        for rel in graph.relations:
            lines.append(
                f"- {rel.source} --[{rel.type} ({rel.confidence})]-> {rel.target} "
                f"(review: {rel.review_status}, provenance: {rel.provenance or 'n/d'})"
            )
        return "\n".join(lines)

    safe_write_text(kg_md_path, _render_md(kg), encoding="utf-8", atomic=True)

    return {"kg_json": str(kg_json_path), "kg_md": str(kg_md_path)}


def build_kg_for_workspace(workspace_root: Path | str, namespace: str | None = None) -> TagKnowledgeGraph:
    workspace_root = Path(workspace_root).resolve()
    semantic_dir = ensure_within_and_resolve(workspace_root, workspace_root / "semantic")
    namespace_resolved = namespace or workspace_root.name

    logger.info(
        "semantic.kg_builder.started",
        extra={"workspace": str(workspace_root), "namespace": namespace_resolved},
    )

    with phase_scope(logger, stage="semantic.tag_kg_builder", customer=namespace_resolved):
        messages = _prepare_input(namespace_resolved, semantic_dir).to_messages()
        raw_output = _invoke_assistant(messages, redact_logs=False)

        kg = TagKnowledgeGraph.from_dict(raw_output)
        kg.namespace = namespace_resolved
        outputs = _save_outputs(semantic_dir, kg)

        logger.info(
            "semantic.kg_builder.completed",
            extra={
                "workspace": str(workspace_root),
                "namespace": namespace_resolved,
                "kg_json": outputs["kg_json"],
                "kg_md": outputs["kg_md"],
            },
        )
        return kg
