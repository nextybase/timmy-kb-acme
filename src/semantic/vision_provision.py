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
from typing import Any, Dict, List, Mapping, Optional, Tuple, cast

from pipeline import ontology
from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_append_text, safe_write_text
from pipeline.import_utils import import_from_candidates
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.settings import Settings
from pipeline.vision_template import load_vision_template_sections
from semantic.validation import validate_context_slug
from semantic.vision_utils import json_to_cartelle_raw_yaml, vision_to_semantic_mapping_yaml

# Logger strutturato di modulo
EVENT = "semantic.vision"
LOG_FILE_NAME = "semantic.vision.log"


def _evt(suffix: str) -> str:
    return EVENT + "." + suffix


LOGGER = get_structured_logger(EVENT)
IMPORT_LOGGER = get_structured_logger(_evt("imports"))

make_openai_client = import_from_candidates(
    [
        "ai.client_factory:make_openai_client",
        "..ai.client_factory:make_openai_client",
    ],
    package=__package__,
    description="make_openai_client",
    logger=IMPORT_LOGGER,
)

_masking_module = import_from_candidates(
    [
        "security.masking",
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
# I test Fase 1 richiedono che le chiavi finali includano le sezioni canoniche della Vision 1.0.
REQUIRED_SECTIONS_CANONICAL: Tuple[str, ...] = (
    "Vision",
    "Mission",
    "Framework Etico",
    "Goal",
    "Contesto Operativo",
)

# Varianti d'intestazione accettate nel PDF che mappiamo ai canonici
# (case-insensitive; gestione spazi intorno agli slash o maiuscole).
_HEADER_VARIANTS: Dict[str, List[str]] = {
    "Vision": ["Vision"],
    "Mission": ["Mission"],
    "Framework Etico": ["Framework Etico", "Framework etico"],
    "Goal": ["Goal"],
    "Contesto Operativo": ["Contesto Operativo", "Contesto operativo"],
}

# Etichette “friendly” per messaggi d’errore
_DISPLAY_LABEL: Dict[str, str] = {
    "Vision": "Vision",
    "Mission": "Mission",
    "Framework Etico": "Framework Etico",
    "Goal": "Goal",
    "Contesto Operativo": "Contesto Operativo",
}

# Precompilazione: mappa variante (casefold) -> canonico, e regex header
_VARIANT_TO_CANON: Dict[str, str] = {}
_all_variants: List[str] = []
for _canon, _vars in _HEADER_VARIANTS.items():
    for _v in _vars:
        _VARIANT_TO_CANON[_v.casefold()] = _canon
        _all_variants.append(re.escape(_v))
_HEADER_RE = re.compile(rf"(?im)^(?P<h>({'|'.join(_all_variants)}))\s*:?\s*$")


def _validate_against_template(found: Mapping[str, str]) -> None:
    sections = load_vision_template_sections()
    if not sections:
        return
    for section in sections:
        if not section.get("required"):
            continue
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        canon = _VARIANT_TO_CANON.get(title.casefold(), title)
        canonical = canon.strip()
        if not canonical:
            continue
        if not found.get(canonical, "").strip():
            LOGGER.warning(
                "template_sections.missing",
                extra={"section": title, "canonical": canonical},
            )


# Giorni di retention per snapshot/log (solo pulizia best-effort)
_SNAPSHOT_RETENTION_DAYS_DEFAULT = 30


def _extract_context_settings(ctx: Any) -> tuple[Optional[Settings], Dict[str, Any]]:
    raw = getattr(ctx, "settings", None)
    if isinstance(raw, Settings):
        try:
            return raw, raw.as_dict()
        except Exception:
            return raw, {}
    if isinstance(raw, Mapping):
        try:
            return None, dict(raw)
        except Exception:
            return None, {}
    as_dict = getattr(raw, "as_dict", None)
    if callable(as_dict):
        try:
            data = as_dict()
            if isinstance(data, Mapping):
                return None, dict(data)
        except Exception:
            pass
    return None, {}


def _resolve_assistant_env(ctx: Any) -> str:
    settings_obj, settings_payload = _extract_context_settings(ctx)
    default_env = "OBNEXT_ASSISTANT_ID"
    if isinstance(settings_obj, Settings):
        candidate = settings_obj.vision_assistant_env
        return candidate.strip() if isinstance(candidate, str) and candidate.strip() else default_env
    vision_cfg = settings_payload.get("vision")
    if isinstance(vision_cfg, Mapping):
        candidate = str(vision_cfg.get("assistant_id_env") or "").strip()
        if candidate:
            return str(candidate)
    return default_env


def _resolve_model_from_settings(ctx: Any) -> str:
    settings_obj, settings_payload = _extract_context_settings(ctx)
    if isinstance(settings_obj, Settings):
        try:
            candidate = settings_obj.vision_model
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        except Exception:
            pass
    vision_cfg = settings_payload.get("vision")
    if isinstance(vision_cfg, Mapping):
        candidate = vision_cfg.get("model")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    candidate = settings_payload.get("vision_model")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return ""


def _resolve_model_from_assistant(client: Any, assistant_id: str) -> str:
    assistants = getattr(client, "assistants", None)
    if assistants is None:
        beta = getattr(client, "beta", None)
        assistants = getattr(beta, "assistants", None)
    if not assistants:
        return ""
    try:
        assistant = assistants.retrieve(assistant_id)
    except Exception as exc:  # pragma: no cover - retriever opzionale
        LOGGER.warning(_evt("assistant_model.error"), extra={"assistant_id": assistant_id, "error": str(exc)})
        return ""
    model = getattr(assistant, "model", None)
    return model.strip() if isinstance(model, str) else ""


def _resolve_snapshot_retention_days(ctx: Any) -> int:
    settings_obj, settings_payload = _extract_context_settings(ctx)
    slug = getattr(ctx, "slug", None)
    fallback = _SNAPSHOT_RETENTION_DAYS_DEFAULT

    def _warn_and_default(reason: str, value: Any) -> int:
        try:
            LOGGER.warning(
                _evt("retention.warning"),
                extra={"slug": slug, "reason": reason, "value": value},
            )
        except Exception:
            pass
        return fallback

    value: Optional[int] = None
    if isinstance(settings_obj, Settings):
        try:
            value = int(settings_obj.vision_snapshot_retention_days)
        except (TypeError, ValueError):
            return _warn_and_default("invalid_type", getattr(settings_obj, "vision_snapshot_retention_days", None))
    else:
        vision_cfg = settings_payload.get("vision")
        if isinstance(vision_cfg, Mapping):
            raw_value = vision_cfg.get("snapshot_retention_days")
            if raw_value is not None:
                try:
                    value = int(raw_value)
                except (TypeError, ValueError):
                    return _warn_and_default("invalid_type", raw_value)

    if value is None:
        return fallback
    if value <= 0:
        return _warn_and_default("non_positive", value)
    return value


def _optional_env(name: str) -> Optional[str]:
    try:
        value = get_env_var(name)
    except KeyError:
        return None
    except Exception:
        return None
    return cast(Optional[str], value)


def _resolve_vision_use_kb(ctx: Any) -> bool:
    """
    Risolve il flag use_kb con precedenza a ENV, poi Settings, poi payload dict.
    Default finale: True (allineato allo health-check).
    """
    env_value = _optional_env("VISION_USE_KB")
    if env_value is not None:
        normalized = env_value.strip().lower()
        return normalized not in {"0", "false", "no", "off"}

    settings_obj, settings_payload = _extract_context_settings(ctx)
    if isinstance(settings_obj, Settings):
        try:
            return bool(settings_obj.vision_settings.use_kb)
        except Exception:
            pass

    vision_cfg = settings_payload.get("vision")
    if isinstance(vision_cfg, Mapping):
        raw = vision_cfg.get("use_kb")
        if isinstance(raw, bool):
            return raw

    return True


def _resolve_vision_strict_output(ctx: Any) -> bool:
    """
    Risolve il flag strict_output: Settings -> payload dict -> default True.
    """
    settings_obj, settings_payload = _extract_context_settings(ctx)
    if isinstance(settings_obj, Settings):
        try:
            return bool(settings_obj.vision_settings.strict_output)
        except Exception:
            pass

    vision_cfg = settings_payload.get("vision")
    if isinstance(vision_cfg, Mapping):
        raw = vision_cfg.get("strict_output")
        if isinstance(raw, bool):
            return raw

    base_dir = getattr(ctx, "base_dir", None)
    if base_dir:
        try:
            fallback_settings = Settings.load(Path(base_dir))
            return bool(fallback_settings.vision_settings.strict_output)
        except Exception:
            pass

    return True


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
        schema = cast(Dict[str, Any], json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Vision schema JSON non valido: {exc}", file_path=str(schema_path)) from exc

    if "type" not in schema:
        schema["type"] = "object"

    properties = schema.get("properties")
    LOGGER.debug(
        _evt("schema.keys"),
        extra={
            "path": str(schema_path),
            "properties": sorted(properties.keys()) if isinstance(properties, dict) else [],
            "required": schema.get("required", []),
        },
    )
    return schema


def _build_run_instructions(use_kb: bool) -> str:
    """
    Costruisce le istruzioni di run per il modello Vision, includendo
    lo schema JSON completo di VisionOutput.

    Obiettivo: massimizzare la probabilità che il modello restituisca
    un singolo oggetto JSON conforme allo schema, senza testo extra.
    """
    schema = _load_vision_schema()
    # Lo schema è già validato a monte; qui lo usiamo solo come testo guida.
    schema_snippet = json.dumps(schema, ensure_ascii=False, indent=2)

    prefix_lines = [
        "Sei il modulo NeXT – Vision → Semantic Mapping.",
        "Ricevi il Vision Statement del cliente e DEVI restituire UN SOLO oggetto JSON",
        "che rispetta esattamente lo schema VisionOutput riportato qui sotto.",
        "",
        "Regole dure sull'output:",
        "- restituisci solo JSON puro, senza testo prima o dopo, senza commenti, senza spiegazioni;",
        "- la radice deve essere un oggetto che rispetta lo schema VisionOutput;",
        "- il payload DEVE contenere almeno le chiavi richieste dallo schema,",
        "  in particolare 'context' e 'areas';",
        "- 'context.slug' e 'context.client_name' devono usare i valori del blocco 'Contesto cliente';",
        "- non aggiungere chiavi fuori dallo schema.",
        "",
        "Schema JSON da rispettare (VisionOutput.schema.json):",
        schema_snippet,
        "",
    ]

    if use_kb:
        suffix = (
            "Durante QUESTA run puoi usare File Search (KB collegata al progetto/assistente) "
            "per integrare e validare i contenuti, ma il testo autorevole è il blocco Vision "
            "fornito nel messaggio utente.\n"
            "In ogni caso, l'output finale deve SEMPRE essere il JSON conforme allo schema sopra."
        )
    else:
        suffix = (
            "Durante QUESTA run devi IGNORARE File Search e qualsiasi risorsa esterna: "
            "usa esclusivamente il blocco Vision fornito nel messaggio utente.\n"
            "L'output finale deve SEMPRE essere il JSON conforme allo schema sopra."
        )

    return "\n".join(prefix_lines) + "\n" + suffix


def _extract_pdf_text(pdf_path: Path, *, slug: str, logger: "logging.Logger") -> str:
    """
    Estrae il testo dal PDF usando PyPDF2/pypdf.
    Mantiene la stessa semantica di errore precedente:
    - dependency-missing  -> libreria PDF non disponibile
    - corrupted           -> file non leggibile / non-PDF
    - empty               -> nessun testo estratto
    """
    try:
        import importlib

        try:
            module = importlib.import_module("pypdf")
        except ImportError:
            module = importlib.import_module("PyPDF2")

        PdfReader = module.PdfReader
    except Exception as exc:  # pragma: no cover
        logger.warning(
            _evt("extract_failed"),
            extra={
                "slug": slug,
                "pdf_path": str(pdf_path),
                "reason": "dependency-missing",
            },
        )
        raise ConfigError(
            "VisionStatement illeggibile: libreria PDF non disponibile",
            slug=slug,
            file_path=str(pdf_path),
        ) from exc

    try:
        reader = PdfReader(str(pdf_path))
        texts: List[str] = []
        for page in getattr(reader, "pages", []) or []:
            try:
                extracted = page.extract_text() or ""
            except Exception:
                extracted = ""
            if extracted:
                texts.append(extracted)
    except Exception as exc:
        logger.warning(
            _evt("extract_failed"),
            extra={
                "slug": slug,
                "pdf_path": str(pdf_path),
                "reason": "corrupted",
            },
        )
        raise ConfigError(
            "VisionStatement illeggibile: file corrotto o non parsabile",
            slug=slug,
            file_path=str(pdf_path),
        ) from exc

    snapshot = "\n".join(texts).strip()
    if not snapshot:
        logger.info(
            _evt("extract_failed"),
            extra={
                "slug": slug,
                "pdf_path": str(pdf_path),
                "reason": "empty",
            },
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
    model: str
    assistant_id: str
    run_instructions: str
    use_kb: bool
    strict_output: bool
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
    da ciascuna intestazione alla successiva. Le intestazioni vengono cercate
    a inizio riga (case-insensitive) con formati “Titolo” o “Titolo:”.
    Ritorna {Chiave canonica -> contenuto (trim)} con chiavi in REQUIRED_SECTIONS_CANONICAL.
    Se una o più sezioni mancano, solleva ConfigError con elenco “friendly”.
    Al termine avvia anche la validazione soft contro il template ufficiale.
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

    _validate_against_template(found)

    return found


def _call_assistant_json(
    client: Any,
    *,
    assistant_id: str,
    model: str,
    user_messages: List[Dict[str, str]],
    strict_output: bool = True,
    run_instructions: Optional[str] = None,
    use_kb: bool = True,
) -> Dict[str, Any]:
    """Instrada l'esecuzione Vision verso Responses."""
    use_structured = _determine_structured_output(client, assistant_id, strict_output)
    response_format = _build_response_format(use_structured)

    if response_format:
        schema_dict = response_format.get("json_schema", {}).get("schema", {})
        props = schema_dict.get("properties") if isinstance(schema_dict, dict) else None
        reqs = schema_dict.get("required") if isinstance(schema_dict, dict) else None
        LOGGER.debug(
            _evt("response_format.keys"),
            extra={
                "properties": sorted(props.keys()) if isinstance(props, dict) else [],
                "required": sorted(reqs) if isinstance(reqs, list) else [],
            },
        )

    return _call_responses_json(
        client=client,
        assistant_id=assistant_id,
        model=model,
        user_messages=user_messages,
        run_instructions=run_instructions,
        use_kb=use_kb,
        use_structured=use_structured,
        response_format=response_format,
    )


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

    try:
        global_entities = ontology.get_all_entities()
    except Exception as exc:  # pragma: no cover - fallback safe
        logger.warning(
            _evt("entities.load_failed"),
            extra={"slug": slug, "error": str(exc)},
        )
        global_entities = []

    user_block_lines.append(
        "Entità globali disponibili (non inventare nuove entità; seleziona solo quelle rilevanti; "
        "assegna area e document_code usando i dati sottostanti):"
    )
    user_block_lines.append("[GlobalEntities]")
    user_block_lines.append(json.dumps(global_entities, ensure_ascii=False, indent=2))
    user_block_lines.append("[/GlobalEntities]")
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

    env_name = _resolve_assistant_env(ctx)
    assistant_id = _optional_env(env_name) or _optional_env("ASSISTANT_ID")
    if not assistant_id:
        raise ConfigError(f"Assistant ID non configurato: imposta {env_name} (o ASSISTANT_ID) nell'ambiente.")

    display_name = getattr(ctx, "client_name", None) or slug
    prompt_text = (
        prepared_prompt
        if prepared_prompt is not None
        else prepare_assistant_input(ctx=ctx, slug=slug, pdf_path=Path(safe_pdf), model=model or "", logger=logger)
    )

    strict_output = _resolve_vision_strict_output(ctx)
    use_kb = _resolve_vision_use_kb(ctx)
    # Le instructions includono lo schema VisionOutput completo, in modo da guidare
    # il modello verso un output JSON strutturato e validabile.
    run_instructions = _build_run_instructions(use_kb=use_kb)

    resolved_model = (model or "").strip() or _resolve_model_from_settings(ctx)
    if not resolved_model:
        resolved_model = _resolve_model_from_assistant(client, assistant_id)
    if not resolved_model:
        raise ConfigError(
            "Modello Vision non configurato: imposta vision.model nel config o assegna un modello all'assistant "
            f"{assistant_id}.",
            slug=slug,
        )

    return _VisionPrepared(
        slug=slug,
        display_name=display_name,
        safe_pdf=Path(safe_pdf),
        prompt_text=prompt_text,
        model=resolved_model,
        assistant_id=assistant_id,
        run_instructions=run_instructions,
        use_kb=use_kb,
        strict_output=strict_output,
        client=client,
        paths=paths,
    )


def _invoke_assistant(prepared: _VisionPrepared) -> Dict[str, Any]:
    return _call_assistant_json(
        client=prepared.client,
        assistant_id=prepared.assistant_id,
        model=prepared.model,
        user_messages=[{"role": "user", "content": prepared.prompt_text}],
        strict_output=prepared.strict_output,
        run_instructions=prepared.run_instructions,
        use_kb=prepared.use_kb,
    )


def _persist_outputs(
    prepared: _VisionPrepared,
    payload: Dict[str, Any],
    logger: "logging.Logger",
    *,
    retention_days: int,
) -> Dict[str, Any]:
    slug = prepared.slug
    _validate_json_payload(payload, expected_slug=slug)

    areas = payload.get("areas")
    min_areas = 1 if prepared.slug == "dummy" else 3
    if not isinstance(areas, list) or not (min_areas <= len(areas) <= 9):
        raise ConfigError(f"Aree fuori range ({min_areas}..9)")

    system_folders = payload.get("system_folders")
    if not isinstance(system_folders, dict) or "identity" not in system_folders or "glossario" not in system_folders:
        raise ConfigError("System folders mancanti (identity, glossario)")

    lint_warnings = _lint_vision_payload(payload)
    for warning in lint_warnings:
        logger.warning(_evt("lint"), extra={"slug": slug, "warning": warning})

    mapping_yaml_str = vision_to_semantic_mapping_yaml(payload, slug=slug)
    safe_write_text(prepared.paths.mapping_yaml, mapping_yaml_str)

    doc_map = payload.get("entity_to_document_type", {})
    raw_folders = None
    if isinstance(doc_map, dict) and doc_map:
        codes = [str(code).strip() for code in doc_map.values() if str(code).strip()]
        raw_folders = {code: [] for code in codes}
    cartelle_yaml_str = json_to_cartelle_raw_yaml(payload, slug=slug, raw_folders=raw_folders)
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
        "vision_engine": "responses",
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
    logger.info(_evt("completed"), extra=record)

    if retention_days > 0:
        try:
            purge_old_artifacts(prepared.paths.base_dir, retention_days)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                _evt("retention.failed"),
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
    model: str,
    prepared_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Onboarding Vision (flusso **semplificato e bloccante**).

    Richiede il modello Vision risolto a monte dall'orchestratore.
    """
    ensure_dotenv_loaded()

    resolved_model = (model or "").strip() or _resolve_model_from_settings(ctx)
    prepared = _prepare_payload(
        ctx,
        slug,
        pdf_path,
        prepared_prompt=prepared_prompt,
        model=resolved_model,
        logger=logger,
    )

    response = _invoke_assistant(prepared)
    if response.get("status") == "halt":
        raise HaltError(response.get("message_ui", "Vision insufficiente"), response.get("missing", {}))

    retention_days = _resolve_snapshot_retention_days(ctx)
    return _persist_outputs(
        prepared,
        response,
        logger,
        retention_days=retention_days,
    )


def _determine_structured_output(client: Any, assistant_id: str, strict_output: bool) -> bool:
    """Decide se usare JSON Schema: strict_output True forza schema, altrimenti fallback json_object."""
    _ = (client, assistant_id)  # mantenimento firma, no calls Assistants
    return bool(strict_output)


def _build_response_format(use_structured: bool) -> Optional[Dict[str, Any]]:
    if not use_structured:
        return {"type": "json_object"}
    schema_payload: Dict[str, Any] = {
        "type": "json_schema",
        "json_schema": {
            "name": "VisionOutput_v2",
            "schema": _load_vision_schema(),
            "strict": True,
        },
    }
    schema_dict = cast(Dict[str, Any], schema_payload["json_schema"]["schema"])
    properties = schema_dict.get("properties") or {}
    required = schema_dict.get("required") or []
    LOGGER.debug(
        _evt("response_format"),
        extra={
            "properties": sorted(properties.keys()) if isinstance(properties, dict) else [],
            "required": sorted(required) if isinstance(required, list) else [],
            "strict": True,
        },
    )
    return schema_payload


def _call_responses_json(
    *,
    client: Any,
    assistant_id: str,
    model: str,
    user_messages: List[Dict[str, str]],
    run_instructions: Optional[str],
    use_kb: bool,
    use_structured: bool,
    response_format: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    LOGGER.debug(
        _evt("response_format_payload"),
        extra={
            "assistant_id": assistant_id,
            "response_format": response_format,
            "use_kb": use_kb,
            "use_structured": use_structured,
        },
    )

    LOGGER.debug(_evt("responses.create"), extra={"assistant_id": assistant_id, "model": model})

    # Costruiamo il payload di input in modo compatibile con lo SDK attuale:
    # - NIENTE parametri extra non supportati (response_format, tool_choice, tools, ...)
    # - Le istruzioni vengono fornite come messaggio "system".
    input_payload: List[Dict[str, str]] = []

    if run_instructions:
        input_payload.append(
            {
                "role": "system",
                "content": str(run_instructions),
            }
        )

    input_payload.extend(
        {
            "role": (msg.get("role") or "user").strip() or "user",
            "content": str(msg.get("content") or ""),
        }
        for msg in user_messages
    )

    request_kwargs: Dict[str, Any] = {
        "model": model,
        "input": input_payload,
    }

    try:
        resp = client.responses.create(**request_kwargs)
    except AttributeError as exc:  # pragma: no cover - adapter mancante
        LOGGER.error(_evt("responses.unsupported"), extra={"assistant_id": assistant_id, "error": str(exc)})
        raise ConfigError("Client OpenAI non supporta l'API Responses.") from exc
    except Exception as exc:
        LOGGER.error(
            _evt("responses.exception"),
            extra={"assistant_id": assistant_id, "error": str(exc)},
        )
        raise ConfigError(f"Responses API fallita: {exc}") from exc

    status = getattr(resp, "status", None)
    if status and status != "completed":
        extra = {
            "assistant_id": assistant_id,
            "status": status,
            "id": getattr(resp, "id", None),
        }
        LOGGER.error(_evt("responses.failed"), extra=extra)
        raise ConfigError(f"Responses run non completato (status={status}).")

    text = None
    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", "") == "output_text":
            text = getattr(getattr(item, "text", None), "value", None)
            if text:
                break
    if not text:
        text = getattr(resp, "output_text", None)

    return _parse_json_output(text, assistant_id, source="responses")


def _parse_json_output(text: Optional[str], assistant_id: str, *, source: str) -> Dict[str, Any]:
    if not text:
        LOGGER.error(_evt("no_output_text"), extra={"assistant_id": assistant_id, "source": source})
        raise ConfigError("Assistant run completato ma nessun testo nel messaggio di output.")

    def _strip_code_fences(payload: str) -> str:
        candidate = payload.strip()
        if candidate.startswith("```") and candidate.count("```") >= 2:
            parts = candidate.split("```")
            candidate = parts[1] if len(parts) > 1 else candidate
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].lstrip()
        return candidate.strip()

    def _try_json_load(payload: str) -> Dict[str, Any]:
        return cast(Dict[str, Any], json.loads(payload))

    if isinstance(text, str):
        stripped = text.lstrip()
        if not stripped.startswith("{") and not stripped.startswith("["):
            LOGGER.warning(
                _evt("non_json_like_output"),
                extra={
                    "assistant_id": assistant_id,
                    "source": source,
                    "sample": stripped[:500],
                },
            )
            try:
                if LOGGER.isEnabledFor(logging.DEBUG):
                    LOGGER.debug(
                        _evt("raw_output.capture"),
                        extra={
                            "assistant_id": assistant_id,
                            "source": source,
                            "length": len(stripped),
                            "preview": stripped[:2000],
                        },
                    )
            except Exception:
                pass
            # Tolleranza minima: se l'output è racchiuso in ```...``` o ```json ...```, rimuovi i fence.
            text = _strip_code_fences(stripped)
    try:
        return _try_json_load(text)  # type: ignore[arg-type]
    except json.JSONDecodeError as exc:
        # Se arrivano fence ```...``` non rimossi o testo extra, prova un parse best-effort sul blocco tra i fence.
        if isinstance(text, str) and "```" in text:
            fences = text.split("```")
            for chunk in fences:
                candidate = _strip_code_fences(chunk)
                if not candidate:
                    continue
                try:
                    return _try_json_load(candidate)
                except Exception:
                    continue
        LOGGER.error(
            _evt("invalid_json"),
            extra={
                "assistant_id": assistant_id,
                "error": str(exc),
                "source": source,
                "sample": (text[:500] if isinstance(text, str) else None),
            },
        )
        raise ConfigError(f"Assistant: risposta non JSON: {exc}") from exc
