# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from timmykb.ai.client_factory import make_openai_client

from .kg_models import TagKnowledgeGraph

logger = get_structured_logger("timmykb.kg_builder")


# ---------------------------------------------------------------------------
# Modelli "raw" per l'input all'assistant
# ---------------------------------------------------------------------------


@dataclass
class RawTag:
    raw_label: str
    contexts: List[str]


@dataclass
class TagKgInput:
    """Payload logico usato per chiamare l'assistant Tag KG Builder."""

    namespace: str
    tags_file: str
    contexts_file: Optional[str]
    tags: List[RawTag]

    def to_assistant_payload(self) -> Dict[str, Any]:
        """Converte il payload nel JSON da passare al messaggio utente."""
        return {
            "namespace": self.namespace,
            "tags_file": self.tags_file,
            "contexts_file": self.contexts_file,
            "tags": [{"raw_label": t.raw_label, "contexts": t.contexts} for t in self.tags],
        }


# ---------- helper parser -------------------------------------------------
_LABEL_CANDIDATES = ("raw_label", "label", "tag", "value", "name")
_CONTEXT_FIELDS = ("contexts", "context", "snippets", "examples")
_META_CONTEXT_FIELDS = ("relative_path", "path", "source", "source_path")


def _normalize_entry(item: Any, default_label: Optional[str] = None) -> dict[str, Any]:
    if isinstance(item, Mapping):
        entry: dict[str, Any] = dict(item)
    else:
        entry = {"raw_label": str(item)} if item is not None else {}
    if default_label and not entry.get("raw_label") and not entry.get("label"):
        entry["raw_label"] = default_label
    return entry


def _iter_tag_entries(source: Any) -> Iterable[dict[str, Any]]:
    if source is None:
        return ()
    if isinstance(source, Mapping):
        for key, value in source.items():
            if isinstance(value, Mapping):
                yield _normalize_entry(value, default_label=key)
            elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                for child in value:
                    yield _normalize_entry(child, default_label=key)
            else:
                yield _normalize_entry(value, default_label=key)
        return ()
    if isinstance(source, Iterable) and not isinstance(source, (str, bytes)):
        for item in source:
            yield _normalize_entry(item)
        return ()
    yield _normalize_entry(source)


def _extract_label(entry: Mapping[str, Any]) -> str:
    for key in _LABEL_CANDIDATES:
        candidate = entry.get(key)
        if isinstance(candidate, str):
            candidate = candidate.strip()
            if candidate:
                return candidate
            continue
        if candidate is not None:
            return str(candidate).strip()
    return ""


def _normalize_contexts(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, Mapping):
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
    if isinstance(value, Iterable):
        contexts: list[str] = []
        for part in value:
            if isinstance(part, str):
                trimmed = part.strip()
                if trimmed:
                    contexts.append(trimmed)
                continue
            if part is None:
                continue
            contexts.append(json.dumps(part, ensure_ascii=False, sort_keys=True))
        return contexts
    return [str(value).strip()]


def _gather_contexts(entry: Mapping[str, Any]) -> list[str]:
    contexts: list[str] = []
    for field in _CONTEXT_FIELDS:
        contexts.extend(_normalize_contexts(entry.get(field)))
    for field in _META_CONTEXT_FIELDS:
        value = entry.get(field)
        if value:
            contexts.append(f"{field}: {value}")
    sources = entry.get("sources")
    if sources:
        contexts.append(json.dumps(sources, ensure_ascii=False, sort_keys=True))

    seen: set[str] = set()
    deduped: list[str] = []
    for ctx in contexts:
        if not ctx:
            continue
        if ctx in seen:
            continue
        seen.add(ctx)
        deduped.append(ctx)
    return deduped


# ---------------------------------------------------------------------------
# Funzioni di caricamento / salvataggio
# ---------------------------------------------------------------------------


def _load_raw_tags(workspace_root: Path) -> TagKgInput:
    """Carica i tag grezzi e i contesti prodotti da tag_onboarding_*."""
    semantic_dir = ensure_within_and_resolve(workspace_root, workspace_root / "semantic")
    tags_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_raw.json")
    contexts_candidate = semantic_dir / "tags_context.jsonl"
    contexts_path: Optional[Path] = None
    if contexts_candidate.exists():
        contexts_path = ensure_within_and_resolve(semantic_dir, contexts_candidate)

    raw_text = read_text_safe(semantic_dir, tags_path)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "Impossibile decodificare tags_raw.json: JSON invalido",
            file_path=str(tags_path),
        ) from exc

    tag_source = data.get("tags") or data.get("entries") or data.get("candidates") or data.get("data")

    raw_tags: List[RawTag] = []
    for entry in _iter_tag_entries(tag_source):
        label = _extract_label(entry)
        if not label:
            continue
        contexts = _gather_contexts(entry)
        raw_tags.append(RawTag(raw_label=label, contexts=contexts))

    if not raw_tags:
        raise ConfigError(
            "Il file tags_raw.json non contiene tag validi",
            file_path=str(tags_path),
        )

    namespace = data.get("namespace") or workspace_root.name

    return TagKgInput(
        namespace=namespace,
        tags_file=str(tags_path),
        contexts_file=str(contexts_path) if contexts_path is not None else None,
        tags=raw_tags,
    )


def _save_kg_json(workspace_root: Path, kg: TagKnowledgeGraph) -> Path:
    """Salva il KG come JSON machine-first."""
    semantic_dir = ensure_within_and_resolve(workspace_root, workspace_root / "semantic")
    output_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.json")
    payload = json.dumps(kg.to_dict(), ensure_ascii=False, indent=2)
    safe_write_text(output_path, payload, encoding="utf-8", atomic=True)
    logger.info(
        "kg_builder.kg_json_saved",
        extra={"workspace": str(workspace_root), "file_path": str(output_path)},
    )
    return output_path


def _render_kg_markdown(kg: TagKnowledgeGraph) -> str:
    """Rende una vista Markdown human-friendly del KG per il Team C."""
    lines: List[str] = []

    lines.append(f"# Knowledge Graph dei tag – namespace `{kg.namespace}`")
    lines.append("")
    lines.append(
        f"- Schema version: `{kg.schema_version}`  "
        f"- Generated by: `{kg.generated_by or 'n/a'}`  "
        f"- Generated at: `{kg.generated_at or 'n/a'}`"
    )
    lines.append("")

    # Tag per categoria
    lines.append("## Tag per categoria")
    tags_by_category: Dict[str, List[Any]] = {}
    for tag in kg.tags:
        tags_by_category.setdefault(tag.category or "uncategorized", []).append(tag)

    for category, tags in sorted(tags_by_category.items(), key=lambda x: x[0]):
        lines.append(f"### {category}")
        lines.append("")
        for t in sorted(tags, key=lambda t: t.label.lower()):
            lines.append(f"- **{t.label}** (`{t.id}`)")
            if t.description:
                lines.append(f"  - Descrizione: {t.description}")
            if t.aliases:
                aliases = ", ".join(t.aliases)
                lines.append(f"  - Alias: {aliases}")
            if t.examples:
                lines.append("  - Esempi:")
                for ex in t.examples[:3]:
                    lines.append(f"    - {ex}")
        lines.append("")

    # Relazioni
    lines.append("## Relazioni tra tag")
    if not kg.relations:
        lines.append("")
        lines.append("_Nessuna relazione proposta dall'assistant._")
    else:
        by_type: Dict[str, List[Any]] = {}
        for rel in kg.relations:
            by_type.setdefault(rel.type, []).append(rel)

        for rel_type, rels in sorted(by_type.items(), key=lambda x: x[0]):
            lines.append(f"### {rel_type}")
            lines.append("")
            for r in sorted(rels, key=lambda r: (r.source.lower(), r.target.lower())):
                lines.append(
                    f"- `{r.source}` → `{r.target}` " f"(confidence={r.confidence:.2f}, review={r.review_status})"
                )
                if r.notes:
                    lines.append(f"  - Note: {r.notes}")
            lines.append("")

    return "\n".join(lines)


def _save_kg_markdown(workspace_root: Path, kg: TagKnowledgeGraph) -> Path:
    """Salva la vista Markdown del KG accanto al JSON."""
    semantic_dir = ensure_within_and_resolve(workspace_root, workspace_root / "semantic")
    output_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.md")
    markdown = _render_kg_markdown(kg)
    safe_write_text(output_path, markdown, encoding="utf-8", atomic=True)
    logger.info(
        "kg_builder.kg_markdown_saved",
        extra={"workspace": str(workspace_root), "file_path": str(output_path)},
    )
    return output_path


# ---------------------------------------------------------------------------
# Integrazione con l'assistant Tag KG Builder
# ---------------------------------------------------------------------------


_ASSISTANT_ENV_NAMES = (
    "TAG_KG_BUILDER_ASSISTANT_ID",
    "TAG_KG_ASSISTANT_ID",
    "OBNEXT_ASSISTANT_ID",
    "ASSISTANT_ID",
)


def _resolve_tag_kg_assistant_id() -> str:
    for env in _ASSISTANT_ENV_NAMES:
        try:
            value = get_env_var(env, default=None)
        except KeyError:
            continue
        if value:
            logger.debug("kg_builder.assistant_id_resolved", extra={"env": env, "assistant_id": value})
            return value
    raise ConfigError(
        "Manca l'assistant ID per il Tag KG Builder. "
        "Imposta TAG_KG_BUILDER_ASSISTANT_ID o TAG_KG_ASSISTANT_ID nelle variabili d'ambiente.",
    )


def _collect_tool_calls(steps_page: Iterable[Any]) -> List[Any]:
    tool_calls: List[Any] = []
    for step in steps_page:
        details = getattr(step, "step_details", None)
        if getattr(details, "type", "") != "tool_calls":
            continue
        tool_calls.extend(getattr(details, "tool_calls", []) or [])
    return tool_calls


def call_openai_tag_kg_assistant(payload: TagKgInput) -> TagKnowledgeGraph:
    """Chiama l'assistant 'Tag KG Builder' e restituisce il KG."""
    assistant_id = _resolve_tag_kg_assistant_id()
    client = make_openai_client()
    thread = client.beta.threads.create()
    user_message = (
        "Costruisci un Knowledge Graph dei tag chiamando esclusivamente la funzione `build_tag_kg`.\n"
        "Utilizza soltanto il payload fornito di seguito e non generare testo libero.\n"
        "Payload:\n"
        f"{json.dumps(payload.to_assistant_payload(), ensure_ascii=False, indent=2)}"
    )
    client.beta.threads.messages.create(thread_id=thread.id, role="user", content=user_message)

    instructions = (
        "Sei il Tag KG Builder. Crea un grafo probabilistico dei tag e restituisci "
        "solo la tool call `build_tag_kg` senza output testuali extra."
    )

    with phase_scope(
        logger,
        stage="tag_kg.call",
        customer=payload.namespace,
    ) as phase:
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
            instructions=instructions,
            tool_choice={"type": "function", "function": {"name": "build_tag_kg"}},
            metadata={"source": "timmykb.kg_builder", "namespace": payload.namespace or ""},
            response_format={"type": "json_object"},
        )
        if run.status != "completed":
            raise ConfigError(
                "L'esecuzione dell'assistant Tag KG Builder non è terminata correttamente.",
                file_path=str(payload.tags_file),
            )

        steps_page = client.beta.threads.runs.steps.list(
            run_id=run.id,
            thread_id=thread.id,
            include=["step_details.tool_calls[*].function"],
            order="asc",
        )
        tool_calls = _collect_tool_calls(steps_page)
        phase.set_artifacts(len(tool_calls))

        if not tool_calls:
            raise ConfigError(
                "Nessuna tool call registrata dal Tag KG Builder.",
                file_path=str(payload.tags_file),
            )

        kg_call = next(
            (call for call in tool_calls if getattr(getattr(call, "function", None), "name", "") == "build_tag_kg"),
            None,
        )
        if not kg_call:
            raise ConfigError(
                "La tool call `build_tag_kg` non è stata emessa dall'assistant.",
                file_path=str(payload.tags_file),
            )

        arguments = getattr(getattr(kg_call, "function", None), "arguments", "")
        if not arguments:
            raise ConfigError(
                "La tool call `build_tag_kg` non ha fornito argomenti.",
                file_path=str(payload.tags_file),
            )

        try:
            payload_dict = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                "Impossibile decodificare gli argomenti restituiti da `build_tag_kg`.",
                file_path=str(payload.tags_file),
            ) from exc

        kg = TagKnowledgeGraph.from_dict(payload_dict)
        logger.info(
            "call_openai_tag_kg.assistant_completed",
            extra={
                "assistant_id": assistant_id,
                "namespace": kg.namespace,
                "tag_count": len(kg.tags),
                "relation_count": len(kg.relations),
            },
        )
        return kg


def build_kg_for_workspace(workspace_root: Path, namespace: Optional[str] = None) -> TagKnowledgeGraph:
    """Orchestra il flusso: carica i tag grezzi, chiama l'assistant, salva il KG.

    - workspace_root: root del workspace Timmy (es. output/timmy-kb-<slug>)
    - namespace: opzionale, se None viene ricavato dai dati dei tag o dal nome directory.
    """
    workspace_root = workspace_root.resolve()
    logger.info("kg_builder.started", extra={"workspace": str(workspace_root)})

    payload = _load_raw_tags(workspace_root)
    if namespace:
        payload.namespace = namespace

    kg = call_openai_tag_kg_assistant(payload)

    _save_kg_json(workspace_root, kg)
    _save_kg_markdown(workspace_root, kg)

    logger.info(
        "kg_builder.completed",
        extra={
            "workspace": str(workspace_root),
            "namespace": kg.namespace,
            "tags": len(kg.tags),
            "relations": len(kg.relations),
        },
    )

    return kg
