# =========================
# File: src/semantic/vision_provision.py
# SPDX-License-Identifier: GPL-3.0-or-later
# =========================
from __future__ import annotations

import inspect
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_append_text, safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from semantic.validation import validate_context_slug
from semantic.vision_ai import SYSTEM_PROMPT  # contratto di prompt condiviso
from semantic.vision_utils import json_to_cartelle_raw_yaml
from src.ai.client_factory import make_openai_client
from src.ingest import get_vision_cfg
from src.security.masking import hash_identifier, mask_paths, sha256_path
from src.security.retention import purge_old_artifacts

_CHAT_COMPLETIONS_MAX_CHARS = 200_000
_SNAPSHOT_RETENTION_DAYS_DEFAULT = 30


def _snapshot_retention_days() -> int:
    raw = (os.getenv("VISION_SNAPSHOT_RETENTION_DAYS") or "").strip()
    if not raw:
        return _SNAPSHOT_RETENTION_DAYS_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        return _SNAPSHOT_RETENTION_DAYS_DEFAULT
    return max(0, value)


# Schema minimo per Structured Outputs (richiede solo 'context' e 'areas')
MIN_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["context", "areas"],
    "properties": {
        "context": {
            "type": "object",
            "additionalProperties": False,
            "required": ["slug", "client_name"],
            "properties": {
                "slug": {"type": "string"},
                "client_name": {"type": "string"},
            },
        },
        "areas": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "ambito", "descrizione", "keywords"],
                "properties": {
                    "key": {"type": "string"},
                    "ambito": {"type": "string"},
                    "descrizione": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "synonyms": {
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
        },
    },
}


def _approx_token_count(text: str, model_hint: Optional[str] = None) -> int:
    """Conta i token provando tiktoken; in fallback usa ≈ 4 char/token."""
    try:
        import tiktoken  # type: ignore

        hint = model_hint or os.getenv("VISION_MODEL") or "gpt-4o-mini"
        try:
            enc = tiktoken.encoding_for_model(hint)  # type: ignore[attr-defined]
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")  # type: ignore[attr-defined]
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _split_by_headings(text: str, headings: Tuple[str, ...] = ("Organization", "Vision", "Mission")) -> List[str]:
    """Spezza il VisionStatement in blocchi/sezioni mantenendo i titoli come ancore semantiche."""
    import re

    t = re.sub(r"\n{3,}", "\n\n", text.strip())
    parts = re.split(r"(?m)^(?=(" + "|".join(map(re.escape, headings)) + r")\s*$)", t)
    sections: List[str] = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if title or body:
            sections.append(f"# {title}\n{body}")
    return [s for s in sections if s.strip()]


def _decide_input_mode(snapshot_text: str, env_override: Optional[str] = None) -> str:
    """
    Ritorna 'inline' | 'vector'.
    Se env = 'inline' | 'vector' forza la scelta, altrimenti AUTO:
    - inline se token stimati <= 15k e testo lineare (>= 1 sezione riconosciuta)
    - vector altrimenti
    """
    mode = (env_override or os.getenv("VISION_INPUT_MODE") or "auto").lower()
    if mode in ("inline", "vector"):
        return mode
    is_small = _approx_token_count(snapshot_text) <= 15_000
    has_sections = len(_split_by_headings(snapshot_text)) >= 1
    return "inline" if (is_small and has_sections) else "vector"


def _extract_pdf_text(pdf_path: Path, *, slug: str, logger: logging.Logger) -> str:
    """Estrae testo dal VisionStatement, fallendo rapidamente per PDF illeggibili o vuoti."""
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "vision_provision.extract_failed", extra={"slug": slug, "pdf_path": str(pdf_path), "reason": "corrupted"}
        )
        raise ConfigError(
            "VisionStatement illeggibile: file corrotto o non parsabile", slug=slug, file_path=str(pdf_path)
        ) from exc

    try:
        with fitz.open(pdf_path) as doc:  # type: ignore[attr-defined]
            texts: List[str] = []
            for page in doc:
                texts.append(page.get_text("text"))
    except Exception as exc:
        logger.warning(
            "vision_provision.extract_failed", extra={"slug": slug, "pdf_path": str(pdf_path), "reason": "corrupted"}
        )
        raise ConfigError(
            "VisionStatement illeggibile: file corrotto o non parsabile", slug=slug, file_path=str(pdf_path)
        ) from exc

    snapshot = "\n".join(texts).strip()
    if not snapshot:
        logger.info(
            "vision_provision.extract_failed", extra={"slug": slug, "pdf_path": str(pdf_path), "reason": "empty"}
        )
        raise ConfigError(
            "VisionStatement vuoto: nessun contenuto testuale estraibile", slug=slug, file_path=str(pdf_path)
        )

    return snapshot


def _write_audit_line(base_dir: Path, record: Dict[str, Any]) -> None:
    """Scrive una riga di audit JSONL in modo atomico e sicuro."""
    payload = json.dumps(record, ensure_ascii=False) + "\n"
    safe_append_text(base_dir, base_dir / "logs" / "vision_provision.log", payload)


@dataclass(frozen=True)
class _Paths:
    base_dir: Path
    semantic_dir: Path
    mapping_yaml: Path
    cartelle_yaml: Path


def _resolve_paths(ctx_base_dir: str) -> _Paths:
    base = Path(ctx_base_dir)
    sem_dir = ensure_within_and_resolve(base, base / "semantic")
    mapping_yaml = ensure_within_and_resolve(sem_dir, sem_dir / "semantic_mapping.yaml")
    cartelle_yaml = ensure_within_and_resolve(sem_dir, sem_dir / "cartelle_raw.yaml")
    return _Paths(base, sem_dir, mapping_yaml, cartelle_yaml)


def _count_cartelle_folders(cartelle_path: Path, *, base_dir: Path) -> Optional[int]:
    try:
        raw = read_text_safe(base_dir, cartelle_path, encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    folders = data.get("folders")
    if isinstance(folders, list):
        return len(folders)
    return None


def _resolve_vector_store_ops(client: Any) -> tuple[Any, Any, Callable[[str, Path, Optional[str]], None], str]:
    """
    Restituisce (create_fn, retrieve_fn, add_fn, add_mode) dove:
      - create_fn(name=...) -> vector_store
      - retrieve_fn(vs_id) -> stato vector_store
      - add_fn(vs_id, file_path, file_id|None) -> associa il PDF al VS
      - add_mode in {"id","upload"} indica se add_fn riceve un file_id oppure fa upload diretto

    Politica: preferisci percorsi "upload_and_poll" / "create_and_poll" (se presenti); in alternativa
    usa namespace .files / .file_batches o beta.vector_store_files.
    """

    def _build_add_callable(method: Any) -> Optional[tuple[Callable[[str, Path, Optional[str]], None], str]]:
        try:
            params = inspect.signature(method).parameters
        except (TypeError, ValueError):
            return None

        if "files" in params:

            def _add(vs_id: str, file_path: Path, _file_id: Optional[str], _method=method) -> None:
                with file_path.open("rb") as handle:
                    _method(vector_store_id=vs_id, files=[handle])

            return _add, "upload"

        if "file" in params:

            def _add(vs_id: str, file_path: Path, _file_id: Optional[str], _method=method) -> None:
                with file_path.open("rb") as handle:
                    _method(vector_store_id=vs_id, file=handle)

            return _add, "upload"

        if "file_ids" in params:

            def _add(vs_id: str, _file_path: Path, file_id: Optional[str], _method=method) -> None:
                if not file_id:
                    raise ConfigError("OpenAI client: file_id mancante per l'associazione al vector store.")
                _method(vector_store_id=vs_id, file_ids=[file_id])

            return _add, "id"

        if "file_id" in params:

            def _add(vs_id: str, _file_path: Path, file_id: Optional[str], _method=method) -> None:
                if not file_id:
                    raise ConfigError("OpenAI client: file_id mancante per l'associazione al vector store.")
                _method(vector_store_id=vs_id, file_id=file_id)

            return _add, "id"

        if "ids" in params:

            def _add(vs_id: str, _file_path: Path, file_id: Optional[str], _method=method) -> None:
                if not file_id:
                    raise ConfigError("OpenAI client: file_id mancante per l'associazione al vector store.")
                _method(vector_store_id=vs_id, ids=[file_id])

            return _add, "id"

        return None

    def _try_namespace(namespace: Any) -> Optional[tuple[Callable[[str, Path, Optional[str]], None], str]]:
        if namespace is None:
            return None
        method_order = (
            "upload_and_poll",  # preferito
            "create_and_poll",
            "batch",
            "create",
            "add",
            "attach",
            "append",
        )
        for name in method_order:
            method = getattr(namespace, name, None)
            if method is None:
                continue
            candidate = _build_add_callable(method)
            if candidate:
                return candidate
        return None

    def _build_ops(
        ns: Any, vs_files_global: Any
    ) -> Optional[tuple[Any, Any, Callable[[str, Path, Optional[str]], None], str]]:
        if ns is None or not hasattr(ns, "create"):
            return None
        retrieve = getattr(ns, "retrieve", None)
        if retrieve is None:
            return None

        def _create_vs(**kwargs: Any) -> Any:
            return ns.create(**kwargs)

        # 1) file_batches.* (upload_and_poll)
        file_batches_ns = getattr(ns, "file_batches", None)
        candidate = _try_namespace(file_batches_ns)
        if candidate:
            add_fn, mode = candidate
            return _create_vs, retrieve, add_fn, mode

        # 2) files.* (create + id / upload)
        files_ns = getattr(ns, "files", None)
        candidate = _try_namespace(files_ns)
        if candidate:
            add_fn, mode = candidate
            return _create_vs, retrieve, add_fn, mode

        # 3) beta.vector_store_files (globale)
        candidate = _try_namespace(vs_files_global)
        if candidate:
            add_fn, mode = candidate
            return _create_vs, retrieve, add_fn, mode

        return None

    beta_ns = getattr(client, "beta", None)
    vs_files_global = getattr(beta_ns, "vector_store_files", None)
    namespaces = [getattr(client, "vector_stores", None), getattr(beta_ns, "vector_stores", None) if beta_ns else None]
    for ns in namespaces:
        result = _build_ops(ns, vs_files_global)
        if result:
            return result

    raise ConfigError("OpenAI client non supporta le vector stores. Aggiorna l'SDK o abilita le beta APIs.")


def _extract_id(obj: Any) -> str:
    if obj is None:
        return ""
    value = getattr(obj, "id", None)
    if value:
        return str(value)
    if isinstance(obj, dict):
        value = obj.get("id")
        if value:
            return str(value)
    return ""


# -----------------------------
# Retry helpers + Files API
# -----------------------------
def _with_retries(
    label: str,
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    logger: Optional[logging.Logger] = None,
) -> Any:
    _log = logger or logging.getLogger("semantic.vision_provision")
    last_exc: Optional[Exception] = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2**i) + random.uniform(0.0, 0.2)
            _log.warning(
                "vision.retry", extra={"op": label, "attempt": i + 1, "error": str(exc), "sleep": round(delay, 2)}
            )
            time.sleep(delay)
    if last_exc is None:
        raise RuntimeError(f"Retry loop ended unexpectedly for operation: {label}")
    raise last_exc


def _upload_pdf_file(client: Any, pdf_path: Path) -> str:
    """Upload PDF su Files API, ritorna file_id (purpose=assistants se supportato)."""
    upload_kwargs: Dict[str, Any] = {}
    try:
        sig = inspect.signature(client.files.create)  # type: ignore[attr-defined]
        if "purpose" in sig.parameters:
            upload_kwargs["purpose"] = "assistants"
    except Exception:
        pass

    def _do() -> Any:
        with pdf_path.open("rb") as fh:
            return client.files.create(file=fh, **upload_kwargs)

    obj = _with_retries("files.create", _do)
    fid = _extract_id(obj)
    if not fid:
        raise ConfigError("Upload file fallito: ID non presente.")
    return fid


# -----------------------------
# Cache locale id file/vector
# -----------------------------
def _fs_cache_path(base_dir: Path) -> Path:
    sem = ensure_within_and_resolve(base_dir, base_dir / "semantic")
    return ensure_within_and_resolve(sem, sem / ".vision_fs.json")


def _load_fs_cache(base_dir: Path) -> Dict[str, Any]:
    p = _fs_cache_path(base_dir)
    if not p.exists():
        return {}
    try:
        raw = read_text_safe(base_dir, p, encoding="utf-8")
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_fs_cache(base_dir: Path, data: Dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    safe_write_text(_fs_cache_path(base_dir), payload)


# -----------------------------
# Engines: assistant / responses / legacy
# -----------------------------
def _call_semantic_mapping_response(
    client: Any,
    *,
    engine: str,
    model: str,
    user_block: str,
    vs_id: str,
    snapshot_text: str,
    inline_sections: List[str],
    strict_output: bool,
    attachment_file_id: Optional[str] = None,
) -> tuple[Dict[str, Any], str]:
    """
    Invoca il modello secondo l'engine richiesto:
      - assistant: usa Threads/Runs dell’Assistant preconfigurato (con file_search).
      - responses: usa Responses API con 'model'. 'tools' e 'tool_resources' separati per File Search.
      - legacy: Chat Completions; nessun File Search (non supportato).
    Ritorna (payload_json, engine_usato).
    """
    logger = logging.getLogger("semantic.vision_provision")
    use_inline = bool(inline_sections)

    # JSON schema strict — stile OpenAI v2 (text.format / response_format)
    json_schema_v2 = {
        "type": "json_schema",
        "name": "vision_semantic_mapping_min",
        "schema": MIN_JSON_SCHEMA,
        "strict": bool(strict_output),
    }

    def _make_user_msgs() -> List[Dict[str, str]]:
        """Costruisce SOLO messaggi USER (niente 'system' qui)."""
        msgs: List[Dict[str, str]] = [{"role": "user", "content": user_block}]
        if use_inline:
            for i, sec in enumerate(inline_sections, start=1):
                msgs.append({"role": "user", "content": f"[DOC SEZIONE {i}]\n{sec}\n[/DOC]"})
        return msgs

    run_instructions = (
        "Durante QUESTA run: ignora File Search e usa esclusivamente i blocchi [DOC] forniti. "
        "Produci solo JSON conforme allo schema. Niente testo fuori JSON."
        if use_inline
        else None
    )

    responses_ns = getattr(client, "responses", None)
    beta_ns = getattr(client, "beta", None)
    beta_responses_ns = getattr(beta_ns, "responses", None) if beta_ns else None
    chat_completions = getattr(getattr(client, "chat", None), "completions", None)

    # --- ENGINE: ASSISTANT (Threads/Runs) ---
    if engine == "assistant":
        assistant_id = os.getenv("OBNEXT_ASSISTANT_ID") or os.getenv("ASSISTANT_ID")
        if not assistant_id:
            # Log coerente con i test esistenti
            logger.warning(
                "vision_provision.assistant_id_missing_fallback",
                extra={"fallback": "responses-inline"},
            )
            # Fallback rapido a responses-inline
            input_msgs: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}] + _make_user_msgs()
            payload: Dict[str, Any] = {
                "model": model,
                "input": input_msgs,
                "text": {"format": json_schema_v2},
            }
            try:
                ns = responses_ns or beta_responses_ns
                if not ns or not hasattr(ns, "create"):
                    raise ConfigError("OpenAI client non espone Responses API per fallback rapido.")
                resp = ns.create(**payload)
                data = getattr(resp, "output_parsed", None)
                if data is None:
                    raise ConfigError("OpenAI responses API non ha restituito output_parsed.")
                return data, "responses-inline"
            except Exception:
                # Come ultima spiaggia: legacy inline
                if not chat_completions or not hasattr(chat_completions, "create"):
                    raise
                data = _invoke_chat_completions_legacy(
                    chat_completions=chat_completions,
                    model=model,
                    snapshot_text=snapshot_text,
                    user_block=user_block,
                    use_inline=True,
                    inline_sections=inline_sections,
                )
                return data, "legacy"

        # Assicura file_search nel profilo (non interrompere se fallisce)
        try:
            a = client.beta.assistants.retrieve(assistant_id)
            tools: List[Dict[str, Any]] = []
            for t in getattr(a, "tools", None) or []:
                tools.append(t if isinstance(t, dict) else {"type": getattr(t, "type", None)})
            if not any((t or {}).get("type") == "file_search" for t in tools):
                tools.append({"type": "file_search"})
            kwargs: Dict[str, Any] = {"tools": tools}
            if vs_id:
                kwargs["tool_resources"] = {"file_search": {"vector_store_ids": [vs_id]}}
            client.beta.assistants.update(assistant_id, **kwargs)
        except Exception as e:
            logger.warning(
                "assistant.tool_resources.update_failed", extra={"assistant_id": assistant_id, "error": str(e)}
            )

        # Thread
        thread = _with_retries("threads.create", lambda: client.beta.threads.create(), logger=logger)

        # Messaggi
        if use_inline:
            for msg in _make_user_msgs():
                _with_retries(
                    "threads.messages.create",
                    lambda m=msg: client.beta.threads.messages.create(
                        thread_id=thread.id, role=m["role"], content=m["content"]
                    ),
                    logger=logger,
                )
        elif attachment_file_id:
            _with_retries(
                "threads.messages.create(attachments)",
                lambda: client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=user_block,
                    attachments=[{"file_id": attachment_file_id, "tools": [{"type": "file_search"}]}],
                ),
                logger=logger,
            )
        else:
            _with_retries(
                "threads.messages.create",
                lambda: client.beta.threads.messages.create(thread_id=thread.id, role="user", content=user_block),
                logger=logger,
            )

        # Run con Structured Outputs (json_schema)
        run = _with_retries(
            "runs.create_and_poll",
            lambda: client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=assistant_id,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "vision_semantic_mapping_min",
                        "schema": MIN_JSON_SCHEMA,
                        "strict": bool(strict_output),
                    },
                },
                instructions=run_instructions if run_instructions else None,
            ),
            logger=logger,
        )

        if getattr(run, "status", None) != "completed":
            raise ConfigError(f"Assistant run non completato (status={getattr(run, 'status', 'n/d')}).")

        msgs = _with_retries(
            "threads.messages.list",
            lambda: client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1),
            logger=logger,
        )

        text = None
        for msg in getattr(msgs, "data", []):
            for part in getattr(msg, "content", None) or []:
                t = getattr(part, "type", None)
                if t == "output_text":
                    text = getattr(getattr(part, "text", None), "value", None)
                elif t == "text":
                    text = getattr(getattr(part, "text", None), "value", None)
                if text:
                    break
            if text:
                break
        if not text:
            raise ConfigError("Assistant run completato ma nessun testo nel messaggio di output.")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Assistant: risposta non JSON: {e}") from e

        label = (
            "assistant-inline"
            if use_inline
            else ("assistant-attachments" if attachment_file_id else "assistant-vector")
        )
        return data, label

    # --- ENGINE: RESPONSES (model) ---
    if engine == "responses":
        input_msgs: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}] + _make_user_msgs()
        payload: Dict[str, Any] = {
            "model": model,
            "input": input_msgs,
            "text": {"format": json_schema_v2},
        }
        if (not use_inline) and vs_id:
            payload["tools"] = [{"type": "file_search"}]
            payload["tool_resources"] = {"file_search": {"vector_store_ids": [vs_id]}}

        def _try(ns: Any) -> Optional[tuple[Dict[str, Any], str]]:
            if not ns or not hasattr(ns, "create"):
                return None
            resp = _with_retries("responses.create", lambda: ns.create(**payload), logger=logger)
            data = getattr(resp, "output_parsed", None)
            if data is None:
                raise ConfigError("OpenAI responses API non ha restituito output_parsed.")
            label = "responses-vector" if ((not use_inline) and vs_id) else "responses-inline"
            return data, label

        out = _try(responses_ns)
        if out:
            return out
        out = _try(beta_responses_ns)
        if out:
            return out

        # Fallback finale su legacy
        if chat_completions and hasattr(chat_completions, "create"):
            logger.warning(
                "vision_provision.responses_fallback_legacy", extra={"requested": "responses", "fallback": "legacy"}
            )
            data = _invoke_chat_completions_legacy(
                chat_completions=chat_completions,
                model=model,
                snapshot_text=snapshot_text,
                user_block=user_block,
                use_inline=use_inline,
                inline_sections=inline_sections,
            )
            return data, "legacy"

        raise ConfigError(
            "OpenAI client non espone Responses API (model). "
            "Aggiorna il pacchetto openai oppure imposta VISION_ENGINE=assistant|legacy."
        )

    # --- ENGINE: LEGACY (chat completions) ---
    if engine == "legacy":
        if not chat_completions or not hasattr(chat_completions, "create"):
            raise ConfigError("OpenAI client non espone Chat Completions API legacy.")
        data = _invoke_chat_completions_legacy(
            chat_completions=chat_completions,
            model=model,
            snapshot_text=snapshot_text,
            user_block=user_block,
            use_inline=use_inline,
            inline_sections=inline_sections,
        )
        return data, "legacy"

    raise ConfigError(f"vision.engine non supportato: {engine!r}")


def _call_semantic_mapping_response_compat(
    client: Any,
    *,
    engine: str,
    **kwargs: Any,
) -> tuple[Dict[str, Any], str]:
    """
    Compatibility layer: quando i test monkeypatchano `_call_semantic_mapping_response`
    con una funzione più “stretta”, filtra i kwargs non supportati (es. `attachment_file_id`).
    Mantiene le nostre nuove feature senza rompere test/estensioni esistenti.
    """
    target = _call_semantic_mapping_response
    try:
        params = inspect.signature(target).parameters
    except Exception:
        params = {}
    filtered = {k: v for k, v in kwargs.items() if k in params}
    # garantiamo che i parametri obbligatori ci siano ancora (se mancanti, lasciamo
    # che la funzione target alzi un errore coerente)
    return target(client, engine=engine, **filtered)


def _invoke_chat_completions_legacy(
    *,
    chat_completions: Any,
    model: str,
    snapshot_text: str,
    user_block: str,
    use_inline: bool,
    inline_sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fallback su Chat Completions (senza file_search)."""
    if use_inline:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_block},
        ]
        for i, sec in enumerate(inline_sections or [], start=1):
            messages.append({"role": "user", "content": f"[DOC SEZIONE {i}]\n{sec}\n[/DOC]"})
    else:
        trimmed_snapshot = snapshot_text[:_CHAT_COMPLETIONS_MAX_CHARS]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{user_block}\n\nVision Statement (testo estratto):\n{trimmed_snapshot}"},
        ]

    chat_resp = chat_completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "vision_semantic_mapping_min",
                "schema": MIN_JSON_SCHEMA,
                "strict": True,
            },
        },
    )
    choices = getattr(chat_resp, "choices", None)
    if not choices:
        raise ConfigError("Chat completions: nessuna choice restituita.")
    first = choices[0]
    message = getattr(first, "message", None) or getattr(first, "delta", None) or first
    content = None
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if not content:
        raise ConfigError("Chat completions: contenuto vuoto.")
    text = content if isinstance(content, str) else getattr(content[0], "text", None)
    if not text:
        raise ConfigError("Chat completions: nessun testo restituito.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Chat completions: risposta non JSON: {exc}") from exc


def _create_vector_store_with_pdf(client: Any, pdf_path: Path, slug: Optional[str] = None) -> str:
    """
    Crea un Vector Store per il cliente e carica il PDF.
    - Usa introspezione via _resolve_vector_store_ops (compat con test che lo monkeypatchano)
    - Retry/backoff su create/upload/attach e retrieve
    - Poll indicizzazione; su timeout → ConfigError
    """
    logger = logging.getLogger("semantic.vision_provision")
    create_vs, retrieve_vs, add_file, add_mode = _resolve_vector_store_ops(client)

    def _retry(fn: Callable[[], Any], what: str) -> Any:
        return _with_retries(what, fn, logger=logger)

    # 1) Create Vector Store
    vs = _retry(lambda: create_vs(name=f"vision-kb-{slug or 'unknown'}"), "vector_stores.create")
    vs_id = _extract_id(vs)
    if not vs_id:
        raise ConfigError("OpenAI client: creazione vector store senza ID.")

    # 2) Upload/attach file (upload diretto o via files.create + attach id)
    if add_mode == "id":

        def _do_upload() -> Any:
            with pdf_path.open("rb") as pdf_file:
                upload_kwargs: Dict[str, Any] = {"file": pdf_file}
                try:
                    sig = inspect.signature(client.files.create)
                    if "purpose" in sig.parameters:
                        upload_kwargs["purpose"] = "assistants"
                except Exception:
                    pass
                return client.files.create(**upload_kwargs)

        upload = _retry(_do_upload, "files.create")
        file_id = _extract_id(upload)
        if not file_id:
            raise ConfigError("OpenAI client: upload del PDF fallito (ID mancante).")
        _retry(lambda: add_file(vs_id, pdf_path, file_id), f"vector_store.add_file[{add_mode}]")
    elif add_mode == "upload":
        _retry(lambda: add_file(vs_id, pdf_path, None), f"vector_store.add_file[{add_mode}]")
    else:
        raise ConfigError(f"OpenAI client: modalità add_file non supportata: {add_mode!r}.")

    # 3) Poll indicizzazione
    completed_val: int = 0
    poll_budget_sec = int(os.getenv("VISION_VECTOR_POLL_SECS", "30"))
    deadline = time.time() + poll_budget_sec
    while time.time() < deadline:
        status = _retry(lambda: retrieve_vs(vs_id), "vector_stores.retrieve")
        file_counts = getattr(status, "file_counts", None)
        if isinstance(file_counts, dict):
            completed_val = int(file_counts.get("completed", 0))
        else:
            completed_val = int(getattr(file_counts, "completed", 0) or 0)
        if completed_val >= 1:
            return vs_id
        time.sleep(0.5)

    logger.warning(
        "vision.vector_store.timeout",
        extra={"vs_id": vs_id, "pdf": str(pdf_path), "completed": int(completed_val)},
    )
    raise ConfigError("Vector store non pronto: file non indicizzato entro il timeout", file_path=str(pdf_path))


def _validate_json_payload(data: Dict[str, Any], *, expected_slug: Optional[str] = None) -> None:
    """
    Valida lo schema minimo del payload e (opzionale) la coerenza dello slug.
    Deve fallire SEMPRE con ConfigError (mai AttributeError/KeyError).
    """
    if not isinstance(data, dict):
        raise ConfigError("Output modello non valido: payload non è un oggetto JSON.")
    if "context" not in data or "areas" not in data:
        raise ConfigError("Output modello non valido: mancano 'context' o 'areas'.")

    ctx = data.get("context")
    areas = data.get("areas")
    if not isinstance(ctx, dict):
        raise ConfigError("Output modello non valido: 'context' deve essere un oggetto.")
    if expected_slug is not None:
        validate_context_slug(data, expected_slug=expected_slug)
    if not isinstance(areas, list) or not areas:
        raise ConfigError("Output modello non valido: 'areas' deve essere una lista non vuota.")


def provision_from_vision(
    ctx: Any,
    logger: logging.Logger,
    *,
    slug: str,
    pdf_path: Path,
    model: str = "gpt-4.1-mini",
    force: bool = False,
) -> Dict[str, Any]:
    """
    Esegue l'onboarding Vision:
    1) snapshot testo
    2) invocazione AI (engine esplicito: assistant | responses | legacy) -> JSON schema
    3) scrittura YAML: semantic_mapping.yaml e cartelle_raw.yaml
    Ritorna metadati utili per UI/audit.
    """
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)
    try:
        safe_pdf = ensure_within_and_resolve(base_dir, pdf_path)
    except ConfigError as e:
        raise e.__class__(str(e), slug=slug, file_path=getattr(e, "file_path", None)) from e
    if not safe_pdf.exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))

    paths = _resolve_paths(str(base_dir))
    paths.semantic_dir.mkdir(parents=True, exist_ok=True)

    # 1) Estrazione testo
    snapshot = _extract_pdf_text(safe_pdf, slug=slug, logger=logger)

    # 2) Config
    cfg = getattr(ctx, "config", None)
    vcfg = get_vision_cfg(cfg)
    engine = (vcfg.get("engine") or "responses").lower()
    engine_env = (os.getenv("VISION_ENGINE") or "").strip().lower()
    if engine_env in {"assistant", "responses", "legacy"}:
        engine = engine_env
    strict_output = bool(vcfg.get("strict_output", True))

    # 3) Client
    client = make_openai_client()

    # 4) Strategia input
    input_mode = _decide_input_mode(snapshot)
    fs_mode_env = (os.getenv("VISION_FS_MODE") or "auto").strip().lower()  # 'auto' | 'attachments' | 'vector'
    fs_mode = fs_mode_env if fs_mode_env in {"auto", "attachments", "vector"} else "auto"

    vs_id: Optional[str] = None
    attachment_file_id: Optional[str] = None
    inline_sections: Optional[List[str]] = None

    # Cache per riuso (se stesso PDF)
    cache = _load_fs_cache(paths.base_dir)
    pdf_hash = sha256_path(safe_pdf)

    # Se serve contesto esterno (documento), proviamo attachments → vector → inline
    if input_mode == "vector":
        used_mode: Optional[str] = None
        vector_error: Optional[str] = None

        def _try_attachments() -> bool:
            nonlocal attachment_file_id, used_mode
            try:
                if cache.get("pdf_hash") == pdf_hash and cache.get("file_id"):
                    attachment_file_id = cache.get("file_id")
                else:
                    attachment_file_id = _upload_pdf_file(client, safe_pdf)
                    _save_fs_cache(paths.base_dir, {"pdf_hash": pdf_hash, "file_id": attachment_file_id})
                used_mode = "attachments"
                return True
            except Exception as exc:
                logging.getLogger("semantic.vision_provision").warning(
                    "vision_provision.attach_failed", extra={"slug": slug, "error": str(exc)}
                )
                return False

        def _try_vector() -> bool:
            nonlocal vs_id, used_mode, vector_error
            try:
                if cache.get("pdf_hash") == pdf_hash and cache.get("vs_id"):
                    vs_id = cache.get("vs_id")
                else:
                    vs_id = _create_vector_store_with_pdf(client, safe_pdf, slug)
                    _save_fs_cache(paths.base_dir, {"pdf_hash": pdf_hash, "vs_id": vs_id})
                used_mode = "vector"
                return True
            except Exception as exc:
                vector_error = str(exc)
                logging.getLogger("semantic.vision_provision").warning(
                    "vision_provision.vector_failed", extra={"slug": slug, "error": vector_error}
                )
                return False

        if fs_mode == "attachments":
            if not _try_attachments():
                inline_sections = _split_by_headings(snapshot)
        elif fs_mode == "vector":
            if not _try_vector():
                inline_sections = _split_by_headings(snapshot)
                if vector_error:
                    logging.getLogger("semantic.vision_provision").warning(
                        "vision_provision.vector_failed_fallback_inline", extra={"slug": slug, "error": vector_error}
                    )
        else:  # auto
            if not _try_attachments():
                if not _try_vector():
                    inline_sections = _split_by_headings(snapshot)
                    if vector_error:
                        logging.getLogger("semantic.vision_provision").warning(
                            "vision_provision.vector_failed_fallback_inline",
                            extra={"slug": slug, "error": vector_error},
                        )
        if used_mode:
            logger.info("vision_provision.fs_mode_selected", extra={"mode": used_mode, "slug": slug})

    if inline_sections is None and input_mode == "inline":
        inline_sections = _split_by_headings(snapshot)

    # 5) Modello effettivo
    model_env = os.getenv("VISION_MODEL")
    effective_model = model_env or vcfg.get("model") or model or "gpt-4.1-mini"

    # 6) Prompt utente
    display_name = getattr(ctx, "client_name", None) or slug
    user_block = (
        "Contesto cliente:\n"
        f"- slug: {slug}\n"
        f"- client_name: {display_name}\n"
        + (
            "\nVision Statement: vedi documento allegato nel contesto (tool file_search)."
            if (attachment_file_id or vs_id) and input_mode == "vector"
            else "\nVision Statement: usa SOLO i blocchi DOC forniti qui sotto."
        )
    )

    # 7) Esecuzione modello (con fallback modelli/engine)
    MODEL_FALLBACKS = {"gpt-4.1-mini": "gpt-4o-mini", "gpt-4o-mini": "gpt-4o", "gpt-4.1": "gpt-4o"}
    tried_models: List[str] = []
    data: Optional[Dict[str, Any]] = None
    engine_used: Optional[str] = None
    current_model = effective_model
    invalid_engine_fallback_done = False

    while True:
        tried_models.append(current_model)
        _call_kwargs = dict(
            model=current_model,
            user_block=user_block,
            vs_id=vs_id or "",
            snapshot_text=snapshot,
            inline_sections=inline_sections or [],
            strict_output=strict_output,
            attachment_file_id=attachment_file_id,
        )
        try:
            # Compat layer: se qualcuno (test) ha monkeypatchato la funzione con
            # una signature senza `attachment_file_id`, filtriamo quel kwarg.
            result = _call_semantic_mapping_response_compat(client, engine=engine, **_call_kwargs)
            data, engine_used = result
            break
        except Exception as exc:
            message = str(exc)
            if vs_id and "file_search" in message and "tools[0].type" in message:
                logging.getLogger("semantic.vision_provision").warning(
                    "vision_provision.responses_vector_unsupported",
                    extra={"slug": slug, "engine": engine, "fallback": "responses-inline"},
                )
                inline_sections = inline_sections or _split_by_headings(snapshot)
                _call_kwargs.update({"vs_id": "", "inline_sections": inline_sections or [], "attachment_file_id": None})
                data, engine_used = _call_semantic_mapping_response_compat(client, engine="responses", **_call_kwargs)
                engine_used = "responses-inline"
                break
            if "invalid model" in message.lower():
                fallback_model = MODEL_FALLBACKS.get(current_model)
                if not invalid_engine_fallback_done:
                    logging.getLogger("semantic.vision_provision").warning(
                        "vision_provision.assistant_invalid_model",
                        extra={
                            "slug": slug,
                            "engine": engine,
                            "invalid_model": current_model,
                            "fallback_engine": "responses-inline",
                        },
                    )
                    engine = "responses"
                    vs_id = ""
                    attachment_file_id = None
                    inline_sections = inline_sections or _split_by_headings(snapshot)
                    invalid_engine_fallback_done = True
                    if fallback_model and fallback_model not in tried_models:
                        current_model = fallback_model
                    continue
                if fallback_model and fallback_model not in tried_models:
                    logging.getLogger("semantic.vision_provision").warning(
                        "vision_provision.model_invalid_fallback",
                        extra={"slug": slug, "invalid_model": current_model, "fallback_model": fallback_model},
                    )
                    current_model = fallback_model
                    continue
            raise

    if data is None or engine_used is None:
        logging.getLogger("semantic.vision_provision").error(
            "vision_provision.no_result",
            extra={
                "slug": slug,
                "engine_requested": engine,
                "engine_used": engine_used,
                "models_tried": tried_models,
                "input_mode": input_mode,
            },
        )
        raise ConfigError("OpenAI non ha restituito un payload valido (data/engine mancanti).")

    # HARD GATE: coerenza slug per prevenire leak inter-cliente
    _validate_json_payload(data, expected_slug=slug)

    # 8) JSON -> YAML (semantic_mapping + cartelle_raw)
    categories: Dict[str, Dict[str, Any]] = {}
    for idx, area in enumerate(data["areas"]):
        raw_keywords = area.get("keywords")
        if raw_keywords is None:
            raise ConfigError(f"Vision payload area #{idx} priva di 'keywords'.", slug=slug)
        if isinstance(raw_keywords, str):
            raw_keywords = [raw_keywords]
        elif not isinstance(raw_keywords, list):
            raise ConfigError(f"Vision payload area #{idx} ha 'keywords' non valido (atteso list/str).", slug=slug)
        keywords = [str(item).strip() for item in raw_keywords if str(item).strip()]
        categories[area["key"]] = {
            "ambito": area["ambito"],
            "descrizione": area["descrizione"],
            "keywords": keywords,
        }

    mapping_payload: Dict[str, Any] = {"context": data["context"], **categories}
    if data.get("synonyms"):
        mapping_payload["synonyms"] = data["synonyms"]

    mapping_yaml_str = yaml.safe_dump(mapping_payload, allow_unicode=True, sort_keys=False, width=100)
    safe_write_text(paths.mapping_yaml, mapping_yaml_str)

    cartelle_yaml_str = json_to_cartelle_raw_yaml(data, slug=slug)
    safe_write_text(paths.cartelle_yaml, cartelle_yaml_str)

    # 9) Audit
    ts = datetime.now(timezone.utc).isoformat()
    try:
        import importlib.metadata as _ilm  # py3.8+: importlib_metadata backport opzionale

        _sdk_version = _ilm.version("openai")
    except Exception:
        _sdk_version = ""
    record = {
        "ts": ts,
        "slug": slug,
        "client_hash": hash_identifier(display_name),
        "pdf_hash": sha256_path(safe_pdf),
        "model": current_model,
        "vision_engine": engine_used,
        "input_mode": input_mode,
        "strict_output": strict_output,
        "yaml_paths": mask_paths(paths.mapping_yaml, paths.cartelle_yaml),
        "sdk_version": _sdk_version,
        "project": os.getenv("OPENAI_PROJECT") or "",
        "base_url": os.getenv("OPENAI_BASE_URL") or "",
        "fs_attachment_file_id": attachment_file_id or "",
        "vector_store_id": vs_id or "",
        "fs_mode_env": fs_mode_env,
    }
    _write_audit_line(paths.base_dir, record)
    logger.info("vision_provision: completato", extra=record)

    # 10) Retention
    retention_days = _snapshot_retention_days()
    if retention_days > 0:
        try:
            purge_old_artifacts(paths.base_dir, retention_days)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning(
                "vision_provision.retention.failed",
                extra={"slug": slug, "error": str(exc), "days": retention_days},
            )

    # Ritorna solo i path dei due YAML richiesti
    return {"mapping": str(paths.mapping_yaml), "cartelle_raw": str(paths.cartelle_yaml)}
