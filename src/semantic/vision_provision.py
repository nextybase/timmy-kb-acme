# =========================
# File: src/semantic/vision_provision.py
# SPDX-License-Identifier: GPL-3.0-or-later
# =========================
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from pipeline.env_utils import ensure_dotenv_loaded, get_bool, get_env_var, get_int
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_append_text, safe_write_text
from pipeline.import_utils import import_from_candidates
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from semantic.validation import validate_context_slug
from semantic.vision_utils import json_to_cartelle_raw_yaml, vision_to_semantic_mapping_yaml

# Logger strutturato di modulo
EVENT = "semantic.vision"
LOG_FILE_NAME = "semantic.vision.log"
LOGGER = get_structured_logger(EVENT)
IMPORT_LOGGER = get_structured_logger(f"{EVENT}.imports")

make_openai_client = import_from_candidates(
    [
        "ai.client_factory:make_openai_client",
        "timmykb.ai.client_factory:make_openai_client",
        "..ai.client_factory:make_openai_client",
    ],
    package=__package__,
    description="make_openai_client",
    logger=IMPORT_LOGGER,
)

_masking_module = import_from_candidates(
    [
        "security.masking",
        "timmykb.security.masking",
        "..security.masking",
    ],
    package=__package__,
    description="security.masking",
    logger=IMPORT_LOGGER,
)
hash_identifier = getattr(_masking_module, "hash_identifier")
mask_paths = getattr(_masking_module, "mask_paths")
sha256_path = getattr(_masking_module, "sha256_path")

purge_old_artifacts = import_from_candidates(
    [
        "security.retention:purge_old_artifacts",
        "timmykb.security.retention:purge_old_artifacts",
        "..security.retention:purge_old_artifacts",
    ],
    package=__package__,
    description="purge_old_artifacts",
    logger=IMPORT_LOGGER,
)


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
    value = cast(int, get_int("VISION_SNAPSHOT_RETENTION_DAYS", default=_SNAPSHOT_RETENTION_DAYS_DEFAULT))
    return max(0, value)


def _optional_env(name: str) -> Optional[str]:
    try:
        value = get_env_var(name)
    except KeyError:
        return None
    except Exception:
        return None
    return cast(Optional[str], value)


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
        return cast(Dict[str, Any], json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Vision schema JSON non valido: {exc}", file_path=str(schema_path)) from exc


def _extract_pdf_text(pdf_path: Path, *, slug: str, logger: "logging.Logger") -> str:
    """
    Estrae il testo dal PDF. Fallisce rapidamente se il file è corrotto o vuoto.
    """
    try:
        import fitz
    except Exception as exc:  # pragma: no cover
        logger.warning(
            f"{EVENT}.extract_failed",
            extra={"slug": slug, "pdf_path": str(pdf_path), "reason": "dependency-missing"},
        )
        raise ConfigError(
            "VisionStatement illeggibile: libreria PDF non disponibile",
            slug=slug,
            file_path=str(pdf_path),
        ) from exc

    try:
        with fitz.open(pdf_path) as doc:
            texts: List[str] = []
            for page in doc:
                texts.append(page.get_text("text"))
    except Exception as exc:
        logger.warning(
            f"{EVENT}.extract_failed",
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
            f"{EVENT}.extract_failed",
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
    safe_append_text(base_dir, base_dir / "logs" / LOG_FILE_NAME, payload)


@dataclass(frozen=True)
class _Paths:
    base_dir: Path
    semantic_dir: Path
    mapping_yaml: Path
    cartelle_yaml: Path


@dataclass(frozen=True)
class _VisionPrepared:
    slug: str
    display_name: str
    safe_pdf: Path
    prompt_text: str
    assistant_id: str
    run_instructions: str
    use_kb: bool
    client: Any
    paths: _Paths


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
    use_kb: bool = True,
) -> Dict[str, Any]:
    """
    Invoca l'Assistant preconfigurato usando Threads/Runs con Structured Outputs (JSON Schema).
    - Usa File Search se abilitato (VISION_USE_KB=1, default) forzando tool_choice=file_search.
    - Restituisce il payload JSON già parsato.
    """
    LOGGER.debug(f"{EVENT}.create_thread", extra={"assistant_id": assistant_id})

    # Recupero modello assistant per capire se supporta response_format=json_schema
    try:
        asst = client.beta.assistants.retrieve(assistant_id)
        asst_model = getattr(asst, "model", "") or ""
    except Exception as exc:  # pragma: no cover - diagnostico best effort
        LOGGER.warning(f"{EVENT}.assistant_retrieve_failed", extra={"assistant_id": assistant_id, "error": str(exc)})
        asst_model = ""

    use_structured = bool(strict_output) and ("gpt-4o-2024-08-06" in asst_model or "gpt-4o-mini" in asst_model)

    thread = client.beta.threads.create()

    for msg in user_messages:
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=msg["content"])

    tool_choice = {"type": "file_search"} if use_kb else "auto"

    response_format = (
        {
            "type": "json_schema",
            "json_schema": {
                "name": "VisionOutput",
                "schema": _load_vision_schema(),
                "strict": True,
            },
        }
        if use_structured
        else {"type": "json_object"}
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant_id,
        response_format=response_format,
        instructions=run_instructions or None,
        tool_choice=tool_choice,
    )

    status = getattr(run, "status", None)
    if status != "completed":
        extra = {
            "assistant_id": assistant_id,
            "run_id": getattr(run, "id", None),
            "status": status,
            "last_error": getattr(run, "last_error", None),
            "incomplete_details": getattr(run, "incomplete_details", None),
        }
        LOGGER.error(f"{EVENT}.run_failed", extra=extra)
        last_error = extra["last_error"] or {}
        reason = (
            getattr(last_error, "message", None)
            or getattr(last_error, "code", None)
            or str(last_error)
            or "sconosciuto"
        )
        raise ConfigError(f"Assistant run non completato (status={status or 'n/d'}; reason={reason}).")

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
        LOGGER.error(f"{EVENT}.no_output_text", extra={"assistant_id": assistant_id})
        raise ConfigError("Assistant run completato ma nessun testo nel messaggio di output.")

    try:
        return cast(Dict[str, Any], json.loads(text))
    except json.JSONDecodeError as e:
        LOGGER.error(
            f"{EVENT}.invalid_json",
            extra={
                "assistant_id": assistant_id,
                "error": str(e),
                "sample": (text[:500] if isinstance(text, str) else None),
            },
        )
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
def prepare_assistant_input(
    ctx: Any,
    slug: str,
    pdf_path: Path,
    model: str,
    logger: "logging.Logger",
) -> str:
    """
    Costruisce il messaggio utente completo da inoltrare all'Assistant.
    Nessun side-effect: legge il PDF, normalizza le sezioni e compone il prompt.
    """
    _ = model  # placeholder per eventuali personalizzazioni future
    snapshot = _extract_pdf_text(pdf_path, slug=slug, logger=logger)
    sections = _parse_required_sections(snapshot)
    display_name = getattr(ctx, "client_name", None) or slug

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
    return "\n".join(user_block_lines)


def _prepare_payload(
    ctx: Any,
    slug: str,
    pdf_path: Path,
    *,
    prepared_prompt: Optional[str],
    model: Optional[str],
    logger: "logging.Logger",
) -> _VisionPrepared:
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)
    try:
        safe_pdf = ensure_within_and_resolve(base_dir, pdf_path)
    except ConfigError as exc:
        raise exc.__class__(str(exc), slug=slug, file_path=getattr(exc, "file_path", None)) from exc
    if not Path(safe_pdf).exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))

    paths = _resolve_paths(str(base_dir))
    paths.semantic_dir.mkdir(parents=True, exist_ok=True)

    client = make_openai_client()

    vision_cfg: Dict[str, Any] = {}
    try:
        vision_cfg = (getattr(ctx, "settings", {}) or {}).get("vision", {}) or {}
    except Exception:
        vision_cfg = {}
    env_name = str(vision_cfg.get("assistant_id_env") or "OBNEXT_ASSISTANT_ID").strip() or "OBNEXT_ASSISTANT_ID"
    assistant_id = _optional_env(env_name) or _optional_env("ASSISTANT_ID")
    if not assistant_id:
        raise ConfigError(f"Assistant ID non configurato: imposta {env_name} (o ASSISTANT_ID) nell'ambiente.")

    display_name = getattr(ctx, "client_name", None) or slug
    prompt_text = (
        prepared_prompt
        if prepared_prompt is not None
        else prepare_assistant_input(ctx=ctx, slug=slug, pdf_path=Path(safe_pdf), model=model or "", logger=logger)
    )

    use_kb = get_bool("VISION_USE_KB", default=True)
    if use_kb:
        run_instructions = (
            "Durante QUESTA run puoi usare **File Search** (KB allegata all'assistente) "
            "per verifiche e contesto. I blocchi del Vision Statement restano la fonte primaria. "
            "Produci SOLO JSON conforme allo schema richiesto, senza testo aggiuntivo."
        )
    else:
        run_instructions = (
            "Durante QUESTA run: ignora File Search e qualsiasi risorsa esterna; "
            "usa esclusivamente i blocchi forniti dall'utente. "
            "Produci SOLO JSON conforme allo schema richiesto, senza testo aggiuntivo."
        )

    return _VisionPrepared(
        slug=slug,
        display_name=display_name,
        safe_pdf=Path(safe_pdf),
        prompt_text=prompt_text,
        assistant_id=assistant_id,
        run_instructions=run_instructions,
        use_kb=use_kb,
        client=client,
        paths=paths,
    )


def _invoke_assistant(prepared: _VisionPrepared) -> Dict[str, Any]:
    return _call_assistant_json(
        client=prepared.client,
        assistant_id=prepared.assistant_id,
        user_messages=[{"role": "user", "content": prepared.prompt_text}],
        strict_output=True,
        run_instructions=prepared.run_instructions,
        use_kb=prepared.use_kb,
    )


def _persist_outputs(
    prepared: _VisionPrepared,
    payload: Dict[str, Any],
    logger: "logging.Logger",
) -> Dict[str, Any]:
    slug = prepared.slug
    _validate_json_payload(payload, expected_slug=slug)

    areas = payload.get("areas")
    if not isinstance(areas, list) or not (3 <= len(areas) <= 9):
        raise ConfigError("Aree fuori range (3..9)")

    system_folders = payload.get("system_folders")
    if not isinstance(system_folders, dict) or "identity" not in system_folders or "glossario" not in system_folders:
        raise ConfigError("System folders mancanti (identity, glossario)")

    lint_warnings = _lint_vision_payload(payload)
    for warning in lint_warnings:
        logger.warning(f"{EVENT}.lint", extra={"slug": slug, "warning": warning})

    mapping_yaml_str = vision_to_semantic_mapping_yaml(payload, slug=slug)
    safe_write_text(prepared.paths.mapping_yaml, mapping_yaml_str)

    cartelle_yaml_str = json_to_cartelle_raw_yaml(payload, slug=slug)
    safe_write_text(prepared.paths.cartelle_yaml, cartelle_yaml_str)

    ts = datetime.now(timezone.utc).isoformat()
    try:
        import importlib.metadata as _ilm

        _sdk_version = _ilm.version("openai")
    except Exception:
        _sdk_version = ""
    record = {
        "ts": ts,
        "slug": slug,
        "client_hash": hash_identifier(prepared.display_name),
        "pdf_hash": sha256_path(prepared.safe_pdf),
        "vision_engine": "assistant-inline",
        "input_mode": "inline-only",
        "strict_output": True,
        "yaml_paths": mask_paths(prepared.paths.mapping_yaml, prepared.paths.cartelle_yaml),
        "sdk_version": _sdk_version,
        "project": _optional_env("OPENAI_PROJECT") or "",
        "base_url": _optional_env("OPENAI_BASE_URL") or "",
        "sections": list(REQUIRED_SECTIONS_CANONICAL),
        "lint_warnings": lint_warnings,
    }
    _write_audit_line(prepared.paths.base_dir, record)
    logger.info(f"{EVENT}.completed", extra=record)

    retention_days = _snapshot_retention_days()
    if retention_days > 0:
        try:
            purge_old_artifacts(prepared.paths.base_dir, retention_days)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                f"{EVENT}.retention.failed",
                extra={"slug": slug, "error": str(exc), "days": retention_days},
            )

    return {
        "mapping": str(prepared.paths.mapping_yaml),
        "cartelle_raw": str(prepared.paths.cartelle_yaml),
    }


def provision_from_vision(
    ctx: Any,
    logger: "logging.Logger",
    *,
    slug: str,
    pdf_path: Path,
    force: bool = False,  # mantenuto per compat con layer UI, qui non fa gating
    model: Optional[str] = None,  # argomento accettato per compat, non usato con Assistant
    prepared_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Onboarding Vision (flusso **semplificato e bloccante**).
    """
    ensure_dotenv_loaded()

    prepared = _prepare_payload(
        ctx,
        slug,
        pdf_path,
        prepared_prompt=prepared_prompt,
        model=model,
        logger=logger,
    )

    response = _invoke_assistant(prepared)
    if response.get("status") == "halt":
        raise HaltError(response.get("message_ui", "Vision insufficiente"), response.get("missing", {}))

    return _persist_outputs(prepared, response, logger)
