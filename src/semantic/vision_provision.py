# =========================
# File: src/semantic/vision_provision.py
# SPDX-License-Identifier: GPL-3.0-or-later
# =========================
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_append_text, safe_write_text
from pipeline.path_utils import ensure_within_and_resolve
from semantic.validation import validate_context_slug
from semantic.vision_utils import json_to_cartelle_raw_yaml
from src.ai.client_factory import make_openai_client
from src.security.masking import hash_identifier, mask_paths, sha256_path
from src.security.retention import purge_old_artifacts

# =========================
# Config/Costanti
# =========================

# JSON schema minimo atteso dall’Assistant
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

# Sezioni obbligatorie nel PDF (intestazioni, insensitive, opzionale “:” a fine riga)
REQUIRED_SECTIONS: Tuple[str, ...] = (
    "Vision",
    "Mission",
    "Goal",
    "Framework etico",
    "Descrizione prodotto/azienda",
    "Descrizione mercato",
)

# Giorni di retention per snapshot/log (solo pulizia best-effort)
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


# =========================
# Utility locali
# =========================


def _extract_pdf_text(pdf_path: Path, *, slug: str, logger: logging.Logger) -> str:
    """
    Estrae il testo dal PDF. Fallisce rapidamente se il file è corrotto o vuoto.
    """
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "vision_provision.extract_failed",
            extra={"slug": slug, "pdf_path": str(pdf_path), "reason": "corrupted"},
        )
        raise ConfigError(
            "VisionStatement illeggibile: file corrotto o non parsabile",
            slug=slug,
            file_path=str(pdf_path),
        ) from exc

    try:
        with fitz.open(pdf_path) as doc:  # type: ignore[attr-defined]
            texts: List[str] = []
            for page in doc:
                texts.append(page.get_text("text"))
    except Exception as exc:
        logger.warning(
            "vision_provision.extract_failed",
            extra={"slug": slug, "pdf_path": str(pdf_path), "reason": "corrupted"},
        )
        raise ConfigError(
            "VisionStatement illeggibile: file corrotto o non parsabile",
            slug=slug,
            file_path=str(pdf_path),
        ) from exc

    snapshot = "\n".join(texts).strip()
    if not snapshot:
        logger.info(
            "vision_provision.extract_failed",
            extra={"slug": slug, "pdf_path": str(pdf_path), "reason": "empty"},
        )
        raise ConfigError(
            "VisionStatement vuoto: nessun contenuto testuale estraibile",
            slug=slug,
            file_path=str(pdf_path),
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


def _parse_required_sections(raw_text: str) -> Dict[str, str]:
    """
    Estrae in modo deterministico le sezioni obbligatorie, tagliando il testo
    da ciascuna intestazione alla successiva. Le intestazioni sono cercate
    a inizio riga, case-insensitive, con due varianti:
      - <titolo>
      - <titolo>:
    Ritorna {Titolo Canonico -> contenuto (trim)}.
    Se una o più sezioni mancano, solleva ConfigError con elenco dei titoli mancanti.
    """
    import re

    # Normalizza righe extra
    text = re.sub(r"\n{3,}", "\n\n", raw_text.strip())

    # Costruisci regex di cattura per tutte le intestazioni
    # ^(Vision|Mission|Goal|Framework etico|Descrizione prodotto/azienda|Descrizione mercato)\s*:?\s*$
    headings_escaped = "|".join(map(re.escape, REQUIRED_SECTIONS))
    header_re = re.compile(rf"(?im)^(?P<h>({headings_escaped}))\s*:?\s*$")

    # Trova tutte le intestazioni con i loro indici
    matches = list(header_re.finditer(text))
    found: Dict[str, str] = {}

    for idx, m in enumerate(matches):
        title = m.group("h").strip()
        start = m.end()
        end = matches[idx + 1].start() if (idx + 1) < len(matches) else len(text)
        body = text[start:end].strip()
        # Canonical: usa la forma in REQUIRED_SECTIONS per coerenza chiave
        # (match può avere casing diverso; normalizziamo mappando per lowercase)
        # Trova il canonico per titolo case-folded
        canon = next(
            (req for req in REQUIRED_SECTIONS if req.casefold() == title.casefold()),
            title,
        )
        found[canon] = body

    missing = [t for t in REQUIRED_SECTIONS if t not in found or not found[t].strip()]
    if missing:
        raise ConfigError(
            "VisionStatement incompleto: sezioni mancanti - " + ", ".join(missing),
            file_path=None,
        )

    return found


def _call_assistant_json(
    client: Any,
    *,
    assistant_id: str,
    user_messages: List[Dict[str, str]],
    strict_output: bool = True,
    run_instructions: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Invoca l'Assistant preconfigurato usando Threads/Runs con Structured Outputs (JSON Schema).
    - Non allega file, non usa File Search, non usa vector store.
    - Restituisce il payload JSON già parsato.
    """
    logger = logging.getLogger("semantic.vision_provision")
    logger.debug("vision_provision: creating assistant thread", extra={"assistant_id": assistant_id})

    # Thread
    thread = client.beta.threads.create()

    # Messaggi utente (solo USER message; il system è nel profilo Assistant)
    for msg in user_messages:
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=msg["content"])

    # Run con response_format = json_schema (strict opzionale)
    run = client.beta.threads.runs.create_and_poll(
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
        instructions=run_instructions or None,
    )

    if getattr(run, "status", None) != "completed":
        raise ConfigError(f"Assistant run non completato (status={getattr(run, 'status', 'n/d')}).")

    # Recupera l’ultimo messaggio e interpreta il testo come JSON
    msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)

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
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Assistant: risposta non JSON: {e}") from e


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


# =========================
# API principale
# =========================


def provision_from_vision(
    ctx: Any,
    logger: logging.Logger,
    *,
    slug: str,
    pdf_path: Path,
    force: bool = False,  # mantenuto per compat con layer UI, qui non fa gating
) -> Dict[str, Any]:
    """
    Onboarding Vision (flusso **semplificato e bloccante**).

    Percorso unico:
      1) Estrai testo dal PDF (PyMuPDF).
      2) Parsifica le 6 sezioni obbligatorie (titoli a inizio riga, case-insensitive).
         Se una manca → ConfigError (bloccante).
      3) Invia **esclusivamente** i blocchi testuali all’Assistant preconfigurato
         (Threads/Runs) con `response_format = json_schema`.
      4) Valida JSON e scrivi:
           - semantic/semantic_mapping.yaml
           - semantic/cartelle_raw.yaml
      5) Log e pulizia retention (best-effort).

    Niente vector store, niente attachments, niente Responses/ChatCompletions, niente fallback.
    Se l’Assistant non è configurato a dovere, l’errore è immediato e bloccante.
    """
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)
    try:
        safe_pdf = ensure_within_and_resolve(base_dir, pdf_path)
    except ConfigError as e:
        raise e.__class__(str(e), slug=slug, file_path=getattr(e, "file_path", None)) from e
    if not Path(safe_pdf).exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))

    paths = _resolve_paths(str(base_dir))
    paths.semantic_dir.mkdir(parents=True, exist_ok=True)

    # 1) Estrazione testo
    snapshot = _extract_pdf_text(Path(safe_pdf), slug=slug, logger=logger)

    # 2) Parsing sezioni obbligatorie
    sections = _parse_required_sections(snapshot)

    # 3) Client OpenAI + Assistant ID (bloccante se assente)
    client = make_openai_client()
    assistant_id = os.getenv("OBNEXT_ASSISTANT_ID") or os.getenv("ASSISTANT_ID")
    if not assistant_id:
        raise ConfigError("Assistant ID non configurato: imposta OBNEXT_ASSISTANT_ID o ASSISTANT_ID.")

    display_name = getattr(ctx, "client_name", None) or slug

    # Costruzione messaggio utente: SOLO blocchi testuali (niente file_search)
    # Forniamo un header chiaro e poi ogni sezione in blocchi marcati.
    user_block_lines = [
        "Contesto cliente:",
        f"- slug: {slug}",
        f"- client_name: {display_name}",
        "",
        "Vision Statement (usa SOLO i blocchi sottostanti):",
    ]
    for title in REQUIRED_SECTIONS:
        user_block_lines.append(f"[{title}]")
        user_block_lines.append(sections[title])
        user_block_lines.append(f"[/{title}]")
    user_block = "\n".join(user_block_lines)

    # Istruzioni run per disabilitare qualsiasi ricerca esterna lato Assistant
    run_instructions = (
        "Durante QUESTA run: ignora File Search e qualsiasi risorsa esterna; "
        "usa esclusivamente i blocchi forniti dall'utente. "
        "Produci SOLO JSON conforme allo schema richiesto, senza testo aggiuntivo."
    )

    # 4) Invocazione Assistant con Structured Outputs
    data = _call_assistant_json(
        client=client,
        assistant_id=assistant_id,
        user_messages=[{"role": "user", "content": user_block}],
        strict_output=True,
        run_instructions=run_instructions,
    )

    # 5) Validazione hard + generazione YAML
    _validate_json_payload(data, expected_slug=slug)

    # semantic_mapping.yaml
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

    # 6) Audit (best-effort) — nessun riferimento a vector/attachments
    ts = datetime.now(timezone.utc).isoformat()
    try:
        import importlib.metadata as _ilm  # py3.8+: backport opzionale

        _sdk_version = _ilm.version("openai")
    except Exception:
        _sdk_version = ""
    record = {
        "ts": ts,
        "slug": slug,
        "client_hash": hash_identifier(display_name),
        "pdf_hash": sha256_path(Path(safe_pdf)),
        "vision_engine": "assistant-inline",
        "input_mode": "inline-only",
        "strict_output": True,
        "yaml_paths": mask_paths(paths.mapping_yaml, paths.cartelle_yaml),
        "sdk_version": _sdk_version,
        "project": os.getenv("OPENAI_PROJECT") or "",
        "base_url": os.getenv("OPENAI_BASE_URL") or "",
        "sections": list(REQUIRED_SECTIONS),
    }
    _write_audit_line(paths.base_dir, record)
    logger.info("vision_provision: completato", extra=record)

    # 7) Retention (best-effort)
    retention_days = _snapshot_retention_days()
    if retention_days > 0:
        try:
            purge_old_artifacts(paths.base_dir, retention_days)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "vision_provision.retention.failed",
                extra={"slug": slug, "error": str(exc), "days": retention_days},
            )

    return {"mapping": str(paths.mapping_yaml), "cartelle_raw": str(paths.cartelle_yaml)}
