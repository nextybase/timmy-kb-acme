# =========================
# File: src/semantic/vision_provision.py
# SPDX-License-Identifier: GPL-3.0-or-later
# =========================
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_append_text, safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from semantic.validation import validate_context_slug
from semantic.vision_utils import json_to_cartelle_raw_yaml, vision_to_semantic_mapping_yaml
from src.ai.client_factory import make_openai_client
from src.security.masking import hash_identifier, mask_paths, sha256_path
from src.security.retention import purge_old_artifacts

# =========================
# Eccezioni specifiche
# =========================


class HaltError(RuntimeError):
    def __init__(self, message_ui: str, missing: Dict[str, Any]) -> None:
        super().__init__(message_ui)
        self.missing = missing


# =========================
# Config/Costanti
# =========================

# CHIAVI CANONICHE utilizzate nel parsing, nel prompt e nella validazione.
# I test Fase 1 richiedono che le chiavi finali includano "Prodotto/Azienda" e "Mercato".
REQUIRED_SECTIONS_CANONICAL: Tuple[str, ...] = (
    "Vision",
    "Mission",
    "Goal",
    "Framework etico",
    "Prodotto/Azienda",
    "Mercato",
)

# Varianti d'intestazione accettate nel PDF che mappiamo ai canonici
# (case-insensitive; gestione spazi intorno allo slash; ":" finale opzionale).
_HEADER_VARIANTS: Dict[str, List[str]] = {
    "Vision": ["Vision"],
    "Mission": ["Mission"],
    "Goal": ["Goal"],
    "Framework etico": ["Framework etico"],
    "Prodotto/Azienda": [
        "Prodotto/Azienda",
        "Prodotto / Azienda",
        "Descrizione prodotto/azienda",
        "Descrizione prodotto / azienda",
    ],
    "Mercato": [
        "Mercato",
        "Descrizione mercato",
    ],
}

# Etichette “friendly” per messaggi d’errore (i test vogliono le versioni estese)
_DISPLAY_LABEL: Dict[str, str] = {
    "Vision": "Vision",
    "Mission": "Mission",
    "Goal": "Goal",
    "Framework etico": "Framework etico",
    "Prodotto/Azienda": "Descrizione prodotto/azienda",
    "Mercato": "Descrizione mercato",
}

# Precompilazione: mappa variante (casefold) -> canonico, e regex header
_VARIANT_TO_CANON: Dict[str, str] = {}
_all_variants: List[str] = []
for _canon, _vars in _HEADER_VARIANTS.items():
    for _v in _vars:
        _VARIANT_TO_CANON[_v.casefold()] = _canon
        _all_variants.append(re.escape(_v))
_HEADER_RE = re.compile(rf"(?im)^(?P<h>({'|'.join(_all_variants)}))\s*:?\s*$")

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


@lru_cache(maxsize=1)
def _vision_schema_path() -> Path:
    """
    Restituisce il path assoluto allo schema VisionOutput, validando che resti nel repo.
    """
    repo_root = Path(__file__).resolve().parents[2]
    schema_path = (repo_root / "schemas" / "VisionOutput.schema.json").resolve()
    try:
        schema_path.relative_to(repo_root)
    except ValueError as exc:
        raise ConfigError("Vision schema fuori dal workspace consentito.") from exc
    if not schema_path.is_file():
        raise ConfigError(f"Vision schema non trovato in {schema_path}")
    return schema_path


@lru_cache(maxsize=1)
def _load_vision_schema() -> Dict[str, Any]:
    """
    Carica lo schema VisionOutput dal filesystem (lazy, cache globale).
    """
    schema_path = _vision_schema_path()
    try:
        raw = read_text_safe(schema_path.parents[0], schema_path, encoding="utf-8")
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Vision schema JSON non valido: {exc}", file_path=str(schema_path)) from exc


def _extract_pdf_text(pdf_path: Path, *, slug: str, logger: logging.Logger) -> str:
    """
    Estrae il testo dal PDF. Fallisce rapidamente se il file è corrotto o vuoto.
    """
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "vision_provision.extract_failed",
            extra={"slug": slug, "pdf_path": str(pdf_path), "reason": "dependency-missing"},
        )
        raise ConfigError(
            "VisionStatement illeggibile: libreria PDF non disponibile",
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
    (base_dir / "logs").mkdir(parents=True, exist_ok=True)
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
    a inizio riga (case-insensitive), con due varianti di sintassi:
      - <titolo>
      - <titolo>:
    Ritorna {Chiave Canonica -> contenuto (trim)} con chiavi in REQUIRED_SECTIONS_CANONICAL.
    Aggiunge anche le alias “Descrizione prodotto/azienda” e “Descrizione mercato”
    per compatibilità con test legacy.
    Se una o più sezioni mancano, solleva ConfigError con elenco “friendly”.
    """
    text = re.sub(r"\n{3,}", "\n\n", raw_text.strip())

    matches = list(_HEADER_RE.finditer(text))
    found: Dict[str, str] = {}

    for idx, m in enumerate(matches):
        title_raw = (m.group("h") or "").strip().rstrip(":")
        # normalizza spazi intorno agli slash per robustezza
        title_norm = re.sub(r"\s*/\s*", "/", title_raw)
        canon = _VARIANT_TO_CANON.get(title_norm.casefold())
        if not canon:
            continue
        start = m.end()
        end = matches[idx + 1].start() if (idx + 1) < len(matches) else len(text)
        body = text[start:end].strip()
        found[canon] = body

    # Validazione su chiavi CANONICHE
    missing_canon = [t for t in REQUIRED_SECTIONS_CANONICAL if t not in found or not found[t].strip()]
    if missing_canon:
        human = ", ".join(_DISPLAY_LABEL.get(m, m) for m in missing_canon)
        raise ConfigError("VisionStatement incompleto: sezioni mancanti - " + human, file_path=None)

    # Alias legacy richiesti da alcuni test (stesso contenuto dei canonici)
    found.setdefault("Descrizione prodotto/azienda", found.get("Prodotto/Azienda", ""))
    found.setdefault("Descrizione mercato", found.get("Mercato", ""))

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

    thread = client.beta.threads.create()

    for msg in user_messages:
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=msg["content"])

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant_id,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "VisionOutput",
                "schema": _load_vision_schema(),
                "strict": bool(strict_output),
            },
        },
        instructions=run_instructions or None,
    )

    status = getattr(run, "status", None)
    if status != "completed":
        raise ConfigError(f"Assistant run non completato (status={status or 'n/d'}).")

    msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=10)

    text = None
    for msg in getattr(msgs, "data", []) or []:
        if getattr(msg, "role", "") != "assistant":
            continue
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


# -------------------------
# Micro-linter non bloccante
# -------------------------
def _lint_vision_payload(data: Dict[str, Any]) -> List[str]:
    """
    Regole soft (no HALT):
      - descrizione_breve <= 400 chars (rev HALT, 01 KB)
      - almeno 3 tipi documentali in documents[] (qualità)
    Ritorna lista di warning testuali.
    """
    warnings: List[str] = []
    areas = data.get("areas") or []
    if not isinstance(areas, list):
        return warnings

    for idx, area in enumerate(areas):
        if not isinstance(area, dict):
            continue
        key = area.get("key") or f"area_{idx}"
        # 1) descrizione_breve
        desc = (area.get("descrizione_breve") or "").strip()
        if len(desc) > 400:
            warnings.append(f"descrizione_breve troppo lunga in '{key}' ({len(desc)} > 400)")

        # 2) documents count
        docs = area.get("documents") or []
        if isinstance(docs, str):
            docs = [docs]
        docs = [str(x).strip() for x in docs if str(x).strip()]
        if len(docs) < 3:
            warnings.append(f"pochi tipi documentali in '{key}' (min 3 consigliati)")

    return warnings


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
    model: Optional[str] = None,  # argomento accettato per compat, non usato con Assistant
) -> Dict[str, Any]:
    """
    Onboarding Vision (flusso **semplificato e bloccante**).
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
    vision_cfg = {}
    try:
        vision_cfg = (getattr(ctx, "settings", {}) or {}).get("vision", {}) or {}
    except Exception:
        vision_cfg = {}
    env_name = str(vision_cfg.get("assistant_id_env") or "OBNEXT_ASSISTANT_ID").strip()
    assistant_id = os.getenv(env_name) or os.getenv("ASSISTANT_ID")
    if not assistant_id:
        raise ConfigError(f"Assistant ID non configurato: imposta {env_name} (o ASSISTANT_ID) nell'ambiente.")

    display_name = getattr(ctx, "client_name", None) or slug

    # Costruzione messaggio utente: SOLO blocchi testuali (niente file_search)
    user_block_lines = [
        "Contesto cliente:",
        f"- slug: {slug}",
        f"- client_name: {display_name}",
        "",
        "Vision Statement (usa SOLO i blocchi sottostanti):",
    ]
    for title in REQUIRED_SECTIONS_CANONICAL:
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

    if data.get("status") == "halt":
        raise HaltError(data.get("message_ui", "Vision insufficiente"), data.get("missing", {}))

    # 5) Validazioni hard + linter soft
    _validate_json_payload(data, expected_slug=slug)

    areas = data.get("areas")
    if not isinstance(areas, list) or not (3 <= len(areas) <= 9):
        raise ConfigError("Aree fuori range (3..9)")

    system_folders = data.get("system_folders")
    if not isinstance(system_folders, dict) or "identity" not in system_folders or "glossario" not in system_folders:
        raise ConfigError("System folders mancanti (identity, glossario)")

    # Linter (non bloccante): warning su QA
    lint_warnings = _lint_vision_payload(data)
    for w in lint_warnings:
        logger.warning("vision_provision.lint", extra={"slug": slug, "warning": w})

    # 6) Scrittura YAML
    mapping_yaml_str = vision_to_semantic_mapping_yaml(data, slug=slug)
    safe_write_text(paths.mapping_yaml, mapping_yaml_str)

    cartelle_yaml_str = json_to_cartelle_raw_yaml(data, slug=slug)
    safe_write_text(paths.cartelle_yaml, cartelle_yaml_str)

    # 7) Audit (best-effort)
    ts = datetime.now(timezone.utc).isoformat()
    try:
        import importlib.metadata as _ilm

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
        "sections": list(REQUIRED_SECTIONS_CANONICAL),
        "lint_warnings": lint_warnings,
    }
    _write_audit_line(paths.base_dir, record)
    logger.info("vision_provision: completato", extra=record)

    # 8) Retention (best-effort)
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
