# =========================
# File: src/semantic/vision_provision.py
# =========================
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_append_text, safe_write_text

# Convenzioni del repo
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from semantic.validation import validate_context_slug

# Ri-uso di schema e prompt dal modulo esistente (contratto unico)
# Nota: gli identificatori nel modulo vision_ai possono essere "interni" (prefisso _),
#       ma qui li importiamo esplicitamente per evitare drift tra definizioni duplicate.
from semantic.vision_ai import SYSTEM_PROMPT  # noqa: E402
from semantic.vision_utils import json_to_cartelle_raw_yaml  # noqa: E402
from src.ai.client_factory import make_openai_client

_CHAT_COMPLETIONS_MAX_CHARS = 200_000

# Schema minimo per Structured Outputs (richiede solo 'context' e 'areas')
MIN_JSON_SCHEMA = {
    "type": "object",
    "required": ["context", "areas"],
    "properties": {
        "context": {
            "type": "object",
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


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_pdf_text(pdf_path: Path) -> str:
    """
    Estrae uno snapshot testuale dal PDF.
    Preferisce PyMuPDF (fitz) se disponibile; in alternativa salva un placeholder.
    """
    try:
        import fitz  # type: ignore

        # Assicura la chiusura del file anche su Windows (evita lock del PDF)
        with fitz.open(pdf_path) as doc:  # type: ignore[attr-defined]
            texts: List[str] = []
            for page in doc:
                texts.append(page.get_text("text"))
        return "\n".join(texts).strip()
    except Exception:
        # Fallback "best effort": non blocca il flusso
        return "Snapshot non disponibile (PyMuPDF non installato o PDF non leggibile)."


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
    import inspect

    def _build_add_callable(method: Any) -> Optional[tuple[Callable[[str, Path, Optional[str]], None], str]]:
        try:
            params = inspect.signature(method).parameters
        except (TypeError, ValueError):
            return None

        if "file_ids" in params:

            def _add(vs_id: str, file_path: Path, file_id: Optional[str], _method=method) -> None:
                if not file_id:
                    raise ConfigError("OpenAI client: file_id mancante per l'associazione al vector store.")
                _method(vector_store_id=vs_id, file_ids=[file_id])

            return _add, "id"
        if "file_id" in params:

            def _add(vs_id: str, file_path: Path, file_id: Optional[str], _method=method) -> None:
                if not file_id:
                    raise ConfigError("OpenAI client: file_id mancante per l'associazione al vector store.")
                _method(vector_store_id=vs_id, file_id=file_id)

            return _add, "id"
        if "ids" in params:

            def _add(vs_id: str, file_path: Path, file_id: Optional[str], _method=method) -> None:
                if not file_id:
                    raise ConfigError("OpenAI client: file_id mancante per l'associazione al vector store.")
                _method(vector_store_id=vs_id, ids=[file_id])

            return _add, "id"
        if "files" in params:

            def _add(vs_id: str, file_path: Path, file_id: Optional[str], _method=method) -> None:
                with file_path.open("rb") as handle:
                    _method(vector_store_id=vs_id, files=[handle])

            return _add, "upload"
        if "file" in params:

            def _add(vs_id: str, file_path: Path, file_id: Optional[str], _method=method) -> None:
                with file_path.open("rb") as handle:
                    _method(vector_store_id=vs_id, file=handle)

            return _add, "upload"
        return None

    def _try_namespace(namespace: Any) -> Optional[tuple[Callable[[str, Path, Optional[str]], None], str]]:
        if namespace is None:
            return None
        method_order = (
            "batch",
            "create_and_poll",
            "create",
            "upload_and_poll",
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

        create_fn = _create_vs

        files_ns = getattr(ns, "files", None)
        candidate = _try_namespace(files_ns)
        if candidate:
            add_fn, mode = candidate
            return create_fn, retrieve, add_fn, mode

        file_batches_ns = getattr(ns, "file_batches", None)
        candidate = _try_namespace(file_batches_ns)
        if candidate:
            add_fn, mode = candidate
            return create_fn, retrieve, add_fn, mode

        candidate = _try_namespace(vs_files_global)
        if candidate:
            add_fn, mode = candidate
            return create_fn, retrieve, add_fn, mode

        return None

    beta_ns = getattr(client, "beta", None)
    vs_files_global = getattr(beta_ns, "vector_store_files", None)

    namespaces = [
        getattr(client, "vector_stores", None),
        getattr(beta_ns, "vector_stores", None) if beta_ns else None,
    ]
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


def _call_semantic_mapping_response(
    client: Any,
    *,
    model: str,
    user_block: str,
    vs_id: str,
    snapshot_text: str,
) -> Dict[str, Any]:
    payload = dict(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_block},
        ],
        tools=[{"type": "file_search", "file_search": {"vector_store_ids": [vs_id]}}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "vision_semantic_mapping_min", "schema": MIN_JSON_SCHEMA},
        },
        temperature=0.2,
    )

    responses_ns = getattr(client, "responses", None)
    if responses_ns and hasattr(responses_ns, "create"):
        resp = responses_ns.create(**payload)
        data = getattr(resp, "output_parsed", None)
        if data is None:
            raise ConfigError("OpenAI responses API non ha restituito output_parsed.")
        return data

    beta_ns = getattr(client, "beta", None)
    if beta_ns:
        beta_resp = getattr(beta_ns, "responses", None)
        if beta_resp and hasattr(beta_resp, "create"):
            resp = beta_resp.create(**payload)
            data = getattr(resp, "output_parsed", None)
            if data is None:
                raise ConfigError("OpenAI beta responses API non ha restituito output_parsed.")
            return data

    chat_completions = getattr(getattr(client, "chat", None), "completions", None)
    if chat_completions and hasattr(chat_completions, "create"):
        trimmed_snapshot = snapshot_text[:_CHAT_COMPLETIONS_MAX_CHARS]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (f"{user_block}\n\n" "Vision Statement (testo estratto):\n" f"{trimmed_snapshot}"),
            },
        ]
        chat_resp = chat_completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "vision_semantic_mapping_min", "schema": MIN_JSON_SCHEMA},
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
        import json

        try:
            data = json.loads(content)
        except Exception as exc:
            raise ConfigError(f"Chat completions: risposta non JSON: {exc}") from exc
        return data

    raise ConfigError(
        "OpenAI client non espone le API responses/chat necessarie. Aggiorna l'SDK o abilita le beta APIs."
    )


def _create_vector_store_with_pdf(client, pdf_path: Path) -> str:
    create_vs, retrieve_vs, add_file, add_mode = _resolve_vector_store_ops(client)

    vs = create_vs(name="vision-kb-runtime")
    vs_id = _extract_id(vs)
    if not vs_id:
        raise ConfigError("OpenAI client: creazione vector store senza ID.")

    if add_mode == "id":
        with pdf_path.open("rb") as pdf_file:
            upload = client.files.create(file=pdf_file, purpose="assistants")
        file_id = _extract_id(upload)
        if not file_id:
            raise ConfigError("OpenAI client: upload del PDF fallito (ID mancante).")
        add_file(vs_id, pdf_path, file_id)
    elif add_mode == "upload":
        add_file(vs_id, pdf_path, None)
    else:
        raise ConfigError(f"OpenAI client: modalità add_file non supportata: {add_mode!r}.")

    completed_val: Optional[int] = None
    for _ in range(60):
        status = retrieve_vs(vs_id)
        file_counts = getattr(status, "file_counts", None)
        if isinstance(file_counts, dict):
            completed_val = file_counts.get("completed")  # type: ignore[assignment]
        else:
            completed_val = getattr(file_counts, "completed", None)
        if completed_val and int(completed_val) >= 1:
            return vs_id
        time.sleep(0.5)

    logging.getLogger("semantic.vision_provision").warning(
        "vision.vector_store.timeout",
        extra={"vs_id": vs_id, "pdf": str(pdf_path), "completed": int(completed_val or 0)},
    )
    raise ConfigError(
        "Vector store non pronto: file non indicizzato entro il timeout",
        file_path=str(pdf_path),
    )


def _validate_json_payload(data: Dict[str, Any], *, expected_slug: Optional[str] = None) -> None:
    """
    Valida lo schema minimo del payload e (opzionale) la coerenza dello slug.
    Deve fallire SEMPRE con ConfigError (mai AttributeError/KeyError).
    """
    # Oggetto radice
    if not isinstance(data, dict):
        raise ConfigError("Output modello non valido: payload non è un oggetto JSON.")

    # Presenza campi base (verifica preliminare)
    if "context" not in data or "areas" not in data:
        raise ConfigError("Output modello non valido: mancano 'context' o 'areas'.")

    # Tipi corretti
    ctx = data.get("context")
    areas = data.get("areas")
    if not isinstance(ctx, dict):
        raise ConfigError("Output modello non valido: 'context' deve essere un oggetto.")
    # Coerenza slug, se richiesta (SSoT)
    if expected_slug is not None:
        validate_context_slug(data, expected_slug=expected_slug)

    # Aree: lista non vuota
    if not isinstance(areas, list) or not areas:
        raise ConfigError("Output modello non valido: 'areas' deve essere una lista non vuota.")


def provision_from_vision(
    ctx,
    logger,
    *,
    slug: str,
    pdf_path: Path,
    model: str = "gpt-4.1-mini",
    force: bool = False,
) -> Dict[str, Any]:
    """
    Esegue l'onboarding Vision:
    1) snapshot testo
    2) invocazione AI (Responses API + file_search) -> JSON schema
    3) scrittura YAML: semantic_mapping.yaml e cartelle_raw.yaml
    Ritorna metadati utili per UI/audit.
    """
    # 0) Base dir dal contesto (obbligatoria per path-safety)
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)
    # 1) Risoluzione sicura del PDF entro il perimetro del workspace
    try:
        safe_pdf = ensure_within_and_resolve(base_dir, pdf_path)
    except ConfigError as e:
        # Arricchisci con slug per diagnosi coerente
        raise e.__class__(str(e), slug=slug, file_path=getattr(e, "file_path", None)) from e
    if not safe_pdf.exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))

    paths = _resolve_paths(str(base_dir))
    paths.semantic_dir.mkdir(parents=True, exist_ok=True)

    # Nota: rimosso meccanismo legacy di hash/skip e snapshot testo
    # La funzione ora produce esclusivamente i due YAML richiesti.

    # 1) Estrazione testo (solo per contesto AI; nessun salvataggio snapshot)
    snapshot = _extract_pdf_text(safe_pdf)

    # 2) Invocazione AI
    client = make_openai_client()
    vs_id = _create_vector_store_with_pdf(client, safe_pdf)

    # Modello: priorità a env VISION_MODEL, fallback al parametro/default
    model_env = os.getenv("VISION_MODEL")
    effective_model = model_env or model or "gpt-4.1-mini"

    # Nome visualizzato nel prompt: preferisci ctx.client_name se presente, altrimenti slug
    display_name = getattr(ctx, "client_name", None) or slug

    user_block = (
        "Contesto cliente:\n"
        f"- slug: {slug}\n"
        f"- client_name: {display_name}\n"
        "\nVision Statement: vedi documento allegato nel contesto (tool file_search)."
    )

    data = _call_semantic_mapping_response(
        client,
        model=effective_model,
        user_block=user_block,
        vs_id=vs_id,
        snapshot_text=snapshot,
    )
    # HARD GATE: coerenza slug per prevenire leak inter-cliente
    _validate_json_payload(data, expected_slug=slug)

    # 3) JSON -> YAML (semantic_mapping + cartelle_raw)
    categories: Dict[str, Dict[str, Any]] = {}
    for idx, area in enumerate(data["areas"]):
        raw_keywords = area.get("keywords")
        if raw_keywords is None:
            raise ConfigError(
                f"Vision payload area #{idx} priva di 'keywords'.",
                slug=slug,
            )
        if isinstance(raw_keywords, str):
            raw_keywords = [raw_keywords]
        elif not isinstance(raw_keywords, list):
            raise ConfigError(
                f"Vision payload area #{idx} ha 'keywords' non valido (atteso list/str).",
                slug=slug,
            )
        keywords = [str(item).strip() for item in raw_keywords if str(item).strip()]
        categories[area["key"]] = {
            "ambito": area["ambito"],
            "descrizione": area["descrizione"],
            "keywords": keywords,
        }

    mapping_payload: Dict[str, Any] = {"context": data["context"], **categories}
    if data.get("synonyms"):
        mapping_payload["synonyms"] = data["synonyms"]

    mapping_yaml_str = yaml.safe_dump(
        mapping_payload,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )
    safe_write_text(paths.mapping_yaml, mapping_yaml_str)

    cartelle_yaml_str = json_to_cartelle_raw_yaml(data, slug=slug)
    safe_write_text(paths.cartelle_yaml, cartelle_yaml_str)

    ts = datetime.now(timezone.utc).isoformat()
    record = {
        "ts": ts,
        "slug": slug,
        "client_name": display_name,
        "pdf": str(safe_pdf),
        "model": effective_model,
        "yaml_paths": {"mapping": str(paths.mapping_yaml), "cartelle_raw": str(paths.cartelle_yaml)},
    }
    _write_audit_line(paths.base_dir, record)
    logger.info("vision_provision: completato", extra=record)

    # Ritorna solo i path dei due YAML richiesti
    return {"mapping": str(paths.mapping_yaml), "cartelle_raw": str(paths.cartelle_yaml)}
