# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from ai.kgraph import invoke_kgraph_messages
from kg_models import TagKnowledgeGraph
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.workspace_layout import WorkspaceLayout

logger = get_structured_logger("kg_builder")


# Prompt interno per il modello KGraph (Responses model-only).
# NOTA: questo è il prompt effettivamente usato in runtime, indipendentemente
# dalla configurazione dell'assistant su dashboard.
_KGRAPH_SYSTEM_PROMPT = """
Sei il componente "Tag KG Builder" del framework NeXT.

RICEVI:
- un singolo messaggio utente con un oggetto JSON che contiene:
  {
    "namespace": "string",
    "tags_file": "string",
    "contexts_file": "string o null",
    "tags": [
      { "raw_label": "string", "contexts": ["string", "..."] },
      ...
    ]
  }

DEVI:
- Restituire SOLO un oggetto JSON valido (niente testo fuori dal JSON, niente markdown).
- Il JSON deve rappresentare un TagKnowledgeGraph con questa struttura di alto livello:

{
  "schema_version": "kg-tags-0.1",
  "namespace": "<dall'input.namespace>",
  "generated_by": "assistant-openai",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "source": {
    "tags_file": "string",
    "contexts_file": "string o null"
  },
  "tags": [ ... ],
  "relations": [ ... ]
}

CAMPO tags (obbligatorio, può essere anche lista vuota):
Ogni elemento ha la forma:

{
  "id": "string (es. 'tag:ai.llm')",
  "label": "string",
  "description": "string",
  "category": "tecnologia | processo | prodotto | ruolo | organizzazione | rischio | dato | cliente | servizio",
  "status": "active | draft | deprecated",
  "language": "string (es. 'it')",
  "aliases": ["string", "..."],
  "examples": ["string", "..."],
  "extra": {}
}

- Usa l'italiano per description, examples, notes, salvo termini tecnici (es. LLM).
- Puoi fondere raw_label simili in un solo tag (usando aliases).

CAMPO relations (facoltativo, può essere lista vuota):
Ogni relazione ha la forma:

{
  "id": "rel:<source-id>-><target-id>#<type>",
  "source": "<id di un tag>",
  "target": "<id di un tag>",
  "type": "BROADER_THAN | NARROWER_THAN | RELATED_TO | ALIAS_OF",
  "confidence": numero tra 0.0 e 1.0,
  "review_status": "pending",
  "provenance": "assistant_v1",
  "notes": "string"
}

VINCOLI:
- Non scrivere MAI testo fuori dall'oggetto JSON.
- Non usare blocchi ```json o markdown.
- Se hai poche informazioni, puoi restituire:
  - "tags": [] e/o "relations": [], ma il JSON deve restare ben formato.
""".strip()


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
        """
        Prepara i messaggi per la Responses API in formato model-only:

        input = [
          {
            "role": "system",
            "content": [
              {"type": "input_text", "text": <istruzioni per JSON-only> }
            ]
          },
          {
            "role": "user",
            "content": [
              {"type": "input_text", "text": "<json con namespace/tags/...>"}
            ]
          }
        ]
        """
        payload = {
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
        }

        return [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": _KGRAPH_SYSTEM_PROMPT,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            },
        ]


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


def _prepare_input(namespace: str, semantic_dir: Path) -> TagKgInput:
    tags_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_raw.json")
    contexts_candidate = semantic_dir / "tags_context.jsonl"
    contexts_path = ensure_within_and_resolve(semantic_dir, contexts_candidate)
    tags_raw, resolved_namespace = _load_tags_raw(tags_path, namespace)
    return TagKgInput(
        namespace=resolved_namespace,
        tags_file=str(tags_path),
        contexts_file=str(contexts_path) if contexts_path.exists() else None,
        tags=tags_raw,
    )


def _load_raw_tags(workspace_root: Path) -> TagKgInput:
    layout = WorkspaceLayout.from_workspace(workspace_root)
    return _prepare_input(layout.slug, layout.semantic_dir)


def _invoke_assistant(
    messages: list[dict[str, Any]],
    *,
    redact_logs: bool,
    assistant_env: Optional[str] = None,
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    return invoke_kgraph_messages(
        messages,
        settings=settings,
        assistant_env=assistant_env,
        redact_logs=redact_logs,
    )


def _save_outputs(semantic_dir: Path, kg: TagKnowledgeGraph) -> dict[str, str]:
    kg_json_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.json")
    kg_md_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.md")

    safe_write_text(
        kg_json_path,
        json.dumps(kg.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
        atomic=True,
    )

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


def build_kg_for_workspace(ctx: ClientContext, *, namespace: str | None = None) -> TagKnowledgeGraph:
    if ctx.repo_root_dir is None:
        raise ConfigError("ClientContext privo di repo_root_dir per il Tag KG Builder.")
    layout = WorkspaceLayout.from_context(ctx)
    namespace_resolved = namespace or layout.slug
    semantic_dir = layout.semantic_dir

    repo_root = layout.repo_root_dir
    repo_root_str = str(repo_root) if repo_root is not None else ""
    logger.info(
        "semantic.kg_builder.started",
        extra={"workspace": repo_root_str, "namespace": namespace_resolved},
    )

    with phase_scope(logger, stage="semantic.tag_kg_builder", customer=namespace_resolved):
        messages = _prepare_input(namespace_resolved, semantic_dir).to_messages()
        raw_output = _invoke_assistant(messages, redact_logs=False, settings=ctx.settings)

        kg = TagKnowledgeGraph.from_dict(raw_output)
        kg.namespace = namespace_resolved
        outputs = _save_outputs(layout.semantic_dir, kg)

        logger.info(
            "semantic.kg_builder.completed",
            extra={
                "workspace": repo_root_str,
                "namespace": namespace_resolved,
                "kg_json": outputs["kg_json"],
                "kg_md": outputs["kg_md"],
            },
        )
        return kg
