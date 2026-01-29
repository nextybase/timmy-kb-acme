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
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, cast

import yaml

from ai.client_factory import make_openai_client
from ai.responses import run_json_model
from ai.types import AssistantConfig
from pipeline import ontology
from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_append_text, safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.vision_template import load_vision_template_sections
from security.masking import hash_identifier, mask_paths, sha256_path
from security.retention import purge_old_artifacts
from semantic.core import compile_document_to_vision_yaml
from semantic.pdf_utils import PdfExtractError, extract_text_from_pdf
from semantic.validation import validate_context_slug
from semantic.vision_utils import vision_to_semantic_mapping_yaml

# Logger strutturato di modulo
EVENT = "semantic.vision"
LOG_FILE_NAME = "semantic.vision.log"


def _evt(suffix: str) -> str:
    return EVENT + "." + suffix


LOGGER = get_structured_logger(EVENT)


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

# Etichette "friendly" per messaggi d'errore
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
_HEADER_RE = re.compile(rf"(?im)^(?P<h>\s*(?:#+\s*)?({'|'.join(_all_variants)})\s*:?\s*)$")


class SectionStatus(str, Enum):
    PRESENT = "present"
    EMPTY = "empty"
    CORRUPT = "corrupt"
    MISSING = "missing"


@dataclass
class VisionSectionReport:
    name: str
    status: SectionStatus
    text: Optional[str] = None
    error: Optional[str] = None


# Lista esplicita dei canonici (riusa l'ordine richiesto dai test)
CANONICAL_SECTIONS: Tuple[str, ...] = REQUIRED_SECTIONS_CANONICAL


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


def _optional_env(name: str) -> Optional[str]:
    raw_env_value = os.environ.get(name)
    if raw_env_value is not None and not str(raw_env_value).strip():
        raise ConfigError(
            f"Variabile ambiente vuota: {name}.",
            code="assistant.env.empty",
            component="vision_provision",
            env=name,
        )
    try:
        value = get_env_var(name)
    except KeyError:
        return None
    except Exception as exc:
        raise ConfigError(
            f"Lettura variabile ambiente fallita: {name}.",
            code="assistant.env.read_failed",
            component="vision_provision",
            env=name,
        ) from exc
    return cast(Optional[str], value.strip() if isinstance(value, str) else value)


def _coerce_flag(value: Optional[bool], default: bool) -> bool:
    """
    Coerces an optional boolean flag with a guaranteed default.
    """
    if value is None:
        return default
    return bool(value)


# =========================
# Utility locali
# =========================


@lru_cache(maxsize=1)
def _vision_schema_path() -> Path:
    """
    Restituisce il path assoluto allo schema VisionOutput, validando che resti nel repo.
    """
    repo_root = Path(__file__).resolve().parents[2]
    schema_path = (repo_root / "src" / "ai" / "schemas" / "VisionOutput.schema.json").resolve()
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
        raise ConfigError("Vision schema JSON non valido.", file_path=str(schema_path)) from exc

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
        "Sei il modulo NeXT - Vision → Semantic Mapping.",
        "Ricevi il Vision Statement del cliente e DEVI restituire UN SOLO oggetto JSON",
        "che rispetta esattamente lo schema VisionOutput riportato qui sotto.",
        "",
        "Regole dure sull'output:",
        "- restituisci solo JSON puro, senza testo prima o dopo, senza commenti, senza spiegazioni;",
        "- la radice deve essere un oggetto che rispetta lo schema VisionOutput;",
        "- il payload DEVE contenere almeno le chiavi richieste dallo schema,",
        "  in particolare 'context' e 'areas';",
        "- 'context.slug' e 'context.client_name' devono usare i valori del blocco 'Contesto cliente';",
        "- per OGNI area in 'areas', 'documents' DEVE essere una lista NON vuota (min 1; consigliato >=3);",
        "- 'system_folders.identity.documents' DEVE essere una lista NON vuota (min 1);",
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


def _build_prompt_from_snapshot(snapshot: str, *, slug: str, ctx: Any, logger: "logging.Logger") -> str:
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
    except Exception as exc:
        raise ConfigError(
            f"Ontology load failed: {exc}",
            slug=slug,
        ) from exc

    user_block_lines.append(
        "Entità globali disponibili (non inventare nuove entità; seleziona solo quelle rilevanti; "
        "assegna area e document_code usando i dati sottostanti):"
    )
    user_block_lines.append("[GlobalEntities]")
    user_block_lines.append(json.dumps(global_entities, ensure_ascii=False, indent=2))
    user_block_lines.append("[/GlobalEntities]")
    return "\n".join(user_block_lines)


def _extract_pdf_text(pdf_path: Path, *, slug: str, logger: "logging.Logger") -> str:
    """
    Percorso di test mantenuto solo per monkeypatch.
    """
    try:
        pages = extract_text_from_pdf(pdf_path)
    except PdfExtractError as exc:
        message = str(exc)
        if "Nessun contenuto" in message or "vuoto" in message.lower() or "empty" in message.lower():
            logger.info(
                "semantic.vision.extract_failed",
                extra={"slug": slug, "file_path": str(pdf_path), "reason": "empty"},
            )
            raise ConfigError(
                "VisionStatement illeggibile: file vuoto o senza testo",
                slug=slug,
                file_path=str(pdf_path),
            ) from exc
        logger.warning(
            "semantic.vision.extract_failed",
            extra={"slug": slug, "file_path": str(pdf_path), "reason": "corrupted"},
        )
        raise ConfigError(
            "VisionStatement illeggibile: file corrotto o non parsabile",
            slug=slug,
            file_path=str(pdf_path),
        ) from exc

    text = "\n\n".join(str(p or "") for p in pages).strip()
    if not text:
        logger.info(
            "semantic.vision.extract_failed",
            extra={"slug": slug, "file_path": str(pdf_path), "reason": "empty"},
        )
        raise ConfigError(
            "VisionStatement illeggibile: file vuoto o senza testo",
            slug=slug,
            file_path=str(pdf_path),
        )
    return text


def _load_vision_yaml_text(repo_root_dir: Path, yaml_path: Path, *, slug: str) -> str:
    """
    Carica il testo Vision dal file YAML generato a monte (visionstatement.yaml).
    Richiede content.full_text presente e non vuoto (hard cut: nessun percorso alternativo su pages[]).
    """
    try:
        safe_yaml = ensure_within_and_resolve(repo_root_dir, yaml_path)
    except ConfigError as exc:
        raise exc.__class__(str(exc), slug=slug, file_path=getattr(exc, "file_path", None)) from exc

    if not Path(safe_yaml).exists():
        raise ConfigError(
            "visionstatement.yaml mancante o non leggibile: esegui prima la compilazione PDF→YAML",
            slug=slug,
            file_path=str(safe_yaml),
        )

    try:
        raw = read_text_safe(repo_root_dir, safe_yaml, encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception as exc:
        raise ConfigError(
            "visionstatement.yaml mancante o non leggibile: esegui prima la compilazione PDF→YAML",
            slug=slug,
            file_path=str(safe_yaml),
        ) from exc

    if not isinstance(data, Mapping):
        raise ConfigError(
            "visionstatement.yaml mancante o non leggibile: contenuto non valido",
            slug=slug,
            file_path=str(safe_yaml),
        )
    content = data.get("content") if isinstance(data, Mapping) else None
    if not isinstance(content, Mapping):
        raise ConfigError(
            "visionstatement.yaml mancante o non leggibile: sezione content assente",
            slug=slug,
            file_path=str(safe_yaml),
        )
    full_text = content.get("full_text")
    if not isinstance(full_text, str) or not full_text.strip():
        raise ConfigError(
            "visionstatement.yaml mancante o non leggibile: content.full_text assente o vuoto",
            slug=slug,
            file_path=str(safe_yaml),
        )
    return full_text.strip()


def _write_audit_line(repo_root_dir: Path, record: Dict[str, Any]) -> None:
    """Scrive una riga di audit JSONL in modo atomico e sicuro."""
    (repo_root_dir / "logs").mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False) + "\n"
    safe_append_text(repo_root_dir, repo_root_dir / "logs" / LOG_FILE_NAME, payload)


@dataclass(frozen=True)
class _Paths:
    repo_root_dir: Path
    semantic_dir: Path
    mapping_yaml: Path


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
    retention_days: int


def _resolve_paths(ctx_repo_root_dir: str) -> _Paths:
    repo_root_dir = Path(ctx_repo_root_dir)
    sem_dir = ensure_within_and_resolve(repo_root_dir, repo_root_dir / "semantic")
    mapping_yaml = ensure_within_and_resolve(sem_dir, sem_dir / "semantic_mapping.yaml")
    return _Paths(repo_root_dir, sem_dir, mapping_yaml)


def _parse_required_sections(raw_text: str) -> Dict[str, str]:
    """
    Analizza le sezioni obbligatorie e restituisce il mapping canonico -> testo.
    Sezioni mancanti/vuote/corrotte generano ConfigError con dettaglio.
    """
    reports = analyze_vision_sections(raw_text)
    _raise_for_section_reports(reports)
    found = {r.name: r.text or "" for r in reports if r.status == SectionStatus.PRESENT}
    _validate_against_template(found)
    return found


def analyze_vision_sections(raw_text: str) -> List[VisionSectionReport]:
    """
    Estrae le sezioni canoniche usando le intestazioni nel testo e classifica lo stato.
    """
    text = re.sub(r"\n{3,}", "\n\n", str(raw_text).strip())

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

    reports: List[VisionSectionReport] = []
    for section in CANONICAL_SECTIONS:
        body = found.get(section, "")
        if section not in found:
            reports.append(VisionSectionReport(name=section, status=SectionStatus.MISSING, text=None))
            continue
        if not body.strip():
            reports.append(VisionSectionReport(name=section, status=SectionStatus.EMPTY, text=body))
            continue
        reports.append(VisionSectionReport(name=section, status=SectionStatus.PRESENT, text=body))

    return reports


def _raise_for_section_reports(reports: List[VisionSectionReport]) -> None:
    missing = [r.name for r in reports if r.status == SectionStatus.MISSING]
    empty = [r.name for r in reports if r.status == SectionStatus.EMPTY]
    corrupt = [r.name for r in reports if r.status == SectionStatus.CORRUPT]

    if not (missing or empty or corrupt):
        return

    parts: List[str] = []
    if missing:
        parts.append("sezioni mancanti - " + ", ".join(_DISPLAY_LABEL.get(m, m) for m in missing))
    if empty:
        parts.append("sezioni vuote - " + ", ".join(_DISPLAY_LABEL.get(e, e) for e in empty))
    if corrupt:
        parts.append("sezioni corrotte - " + ", ".join(_DISPLAY_LABEL.get(c, c) for c in corrupt))

    prefix = "VisionStatement non valido: " if corrupt else "VisionStatement incompleto: "
    raise ConfigError(prefix + "; ".join(parts), file_path=None)


def debug_analyze_vision_sections_from_yaml(yaml_path: Path) -> Tuple[str, List[VisionSectionReport]]:
    """
    Carica visionstatement.yaml, estrae il testo come farebbe il runtime e ritorna testo+report.
    In caso di file invalido solleva ConfigError (hard cut: nessuna degradazione).
    """
    text = _load_vision_yaml_text(yaml_path.parent, yaml_path, slug=yaml_path.parent.name or "vision")
    reports = analyze_vision_sections(text)
    return text, reports


def _call_assistant_json(
    client: Any,
    *,
    assistant_id: str,
    model: str,
    user_messages: List[Dict[str, str]],
    strict_output: bool = True,
    run_instructions: Optional[str] = None,
    use_kb: bool = True,
    slug: Optional[str] = None,
    retention_days: Optional[int] = None,
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

    invocation: dict[str, Any] = {
        "component": "vision",
        "operation": "vision.provision",
        "assistant_id": assistant_id,
        "strict_output": strict_output,
        "use_kb": use_kb,
    }
    if retention_days is not None:
        invocation["retention_days"] = retention_days
    if slug:
        invocation["request_tag"] = slug

    return _call_responses_json(
        client=client,
        assistant_id=assistant_id,
        model=model,
        user_messages=user_messages,
        run_instructions=run_instructions,
        use_kb=use_kb,
        use_structured=use_structured,
        response_format=response_format,
        invocation=invocation,
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
def _ensure_vision_yaml_and_prompt_from_pdf(ctx: Any, slug: str, pdf_path: Path, logger: "logging.Logger") -> str:
    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        raise ConfigError("Context privo di repo_root_dir per Vision onboarding.", slug=slug)
    try:
        safe_pdf = ensure_within_and_resolve(repo_root_dir, pdf_path)
    except ConfigError as exc:
        raise exc.__class__(str(exc), slug=slug, file_path=getattr(exc, "file_path", None)) from exc
    yaml_path = vision_yaml_workspace_path(Path(repo_root_dir), pdf_path=Path(safe_pdf))
    if not yaml_path.exists():
        try:
            snapshot = _extract_pdf_text(safe_pdf, slug=slug, logger=logger)
        except Exception:
            snapshot = None
        if snapshot:
            return _build_prompt_from_snapshot(snapshot, slug=slug, ctx=ctx, logger=logger)
        try:
            compile_document_to_vision_yaml(safe_pdf, yaml_path)
        except Exception as exc:
            raise ConfigError(
                "visionstatement.yaml mancante o non leggibile: esegui prima la compilazione PDF→YAML",
                slug=slug,
                file_path=str(yaml_path),
            ) from exc
    snapshot = _load_vision_yaml_text(Path(repo_root_dir), yaml_path, slug=slug)
    return _build_prompt_from_snapshot(snapshot, slug=slug, ctx=ctx, logger=logger)


def _prepare_payload(
    ctx: Any,
    slug: str,
    pdf_path: Path,
    *,
    prepared_prompt: Optional[str],
    config: AssistantConfig,
    logger: "logging.Logger",
    retention_days: int,
) -> _VisionPrepared:
    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        raise ConfigError("Context privo di repo_root_dir per Vision onboarding.", slug=slug)
    try:
        safe_pdf = ensure_within_and_resolve(repo_root_dir, pdf_path)
    except ConfigError as exc:
        raise exc.__class__(str(exc), slug=slug, file_path=getattr(exc, "file_path", None)) from exc
    if not Path(safe_pdf).exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))
    if not Path(safe_pdf).exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))

    paths = _resolve_paths(str(repo_root_dir))
    paths.semantic_dir.mkdir(parents=True, exist_ok=True)

    client = make_openai_client()

    use_kb_flag = _coerce_flag(config.use_kb, True)
    strict_output_flag = _coerce_flag(config.strict_output, True)

    display_name = getattr(ctx, "client_name", None) or slug
    prompt_text = (
        prepared_prompt
        if prepared_prompt is not None
        else prepare_assistant_input_with_config(
            ctx=ctx,
            slug=slug,
            pdf_path=Path(safe_pdf),
            config=config,
            logger=logger,
        )
    )

    # Le instructions includono lo schema VisionOutput completo, in modo da guidare
    # il modello verso un output JSON strutturato e validabile.
    run_instructions = _build_run_instructions(use_kb=use_kb_flag)

    return _VisionPrepared(
        slug=slug,
        display_name=display_name,
        safe_pdf=Path(safe_pdf),
        prompt_text=prompt_text,
        model=config.model,
        assistant_id=config.assistant_id,
        run_instructions=run_instructions,
        use_kb=use_kb_flag,
        strict_output=strict_output_flag,
        client=client,
        paths=paths,
        retention_days=retention_days,
    )


def _build_prompt_from_yaml_path(
    ctx: Any,
    slug: str,
    yaml_path: Path,
    logger: "logging.Logger",
) -> str:
    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        raise ConfigError("Context privo di repo_root_dir per Vision onboarding.", slug=slug)
    snapshot = _load_vision_yaml_text(Path(repo_root_dir), yaml_path, slug=slug)
    return _build_prompt_from_snapshot(snapshot, slug=slug, ctx=ctx, logger=logger)


def prepare_assistant_input_with_config(
    ctx: Any,
    slug: str,
    pdf_path: Path,
    *,
    config: AssistantConfig,
    logger: "logging.Logger",
) -> str:
    """
    Variante che accetta una configurazione Assembly risolta in anticipo.
    """
    _ = config  # kept for symmetry; prompt generation does not depend on model.
    return _ensure_vision_yaml_and_prompt_from_pdf(ctx=ctx, slug=slug, pdf_path=pdf_path, logger=logger)


def prepare_assistant_input_from_yaml_with_config(
    ctx: Any,
    slug: str,
    yaml_path: Path,
    *,
    config: AssistantConfig,
    logger: "logging.Logger",
) -> str:
    """
    Variante YAML-first che usa la configurazione risolta dal registry prima di
    costruire il prompt.
    """
    _ = config
    return _build_prompt_from_yaml_path(ctx=ctx, slug=slug, yaml_path=yaml_path, logger=logger)


def _prepare_payload_from_yaml(
    ctx: Any,
    slug: str,
    yaml_path: Path,
    *,
    prepared_prompt: Optional[str],
    config: AssistantConfig,
    logger: "logging.Logger",
    retention_days: int,
) -> _VisionPrepared:
    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        raise ConfigError("Context privo di repo_root_dir per Vision onboarding.", slug=slug)
    try:
        safe_yaml = ensure_within_and_resolve(repo_root_dir, yaml_path)
    except ConfigError as exc:
        raise exc.__class__(str(exc), slug=slug, file_path=getattr(exc, "file_path", None)) from exc
    if not Path(safe_yaml).exists():
        raise ConfigError(
            "visionstatement.yaml mancante o non leggibile: esegui prima la compilazione PDF→YAML",
            slug=slug,
            file_path=str(safe_yaml),
        )

    paths = _resolve_paths(str(repo_root_dir))
    paths.semantic_dir.mkdir(parents=True, exist_ok=True)

    client = make_openai_client()
    snapshot = _load_vision_yaml_text(Path(repo_root_dir), Path(safe_yaml), slug=slug)

    display_name = getattr(ctx, "client_name", None) or slug
    prompt_text = (
        prepared_prompt
        if prepared_prompt is not None
        else _build_prompt_from_snapshot(snapshot, slug=slug, ctx=ctx, logger=logger)
    )

    use_kb_flag = _coerce_flag(config.use_kb, True)
    strict_output_flag = _coerce_flag(config.strict_output, True)
    run_instructions = _build_run_instructions(use_kb=use_kb_flag)

    return _VisionPrepared(
        slug=slug,
        display_name=display_name,
        safe_pdf=Path(safe_yaml),
        prompt_text=prompt_text,
        model=config.model,
        assistant_id=config.assistant_id,
        run_instructions=run_instructions,
        use_kb=use_kb_flag,
        strict_output=strict_output_flag,
        client=client,
        paths=paths,
        retention_days=retention_days,
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
        slug=prepared.slug,
        retention_days=prepared.retention_days,
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
        "yaml_paths": mask_paths(prepared.paths.mapping_yaml),
        "sdk_version": _sdk_version,
        "project": _optional_env("OPENAI_PROJECT") or "",
        "base_url": _optional_env("OPENAI_BASE_URL") or "",
        "sections": list(REQUIRED_SECTIONS_CANONICAL),
        "lint_warnings": lint_warnings,
    }
    _write_audit_line(prepared.paths.repo_root_dir, record)
    logger.info(_evt("completed"), extra=record)

    if retention_days > 0:
        try:
            purge_old_artifacts(prepared.paths.repo_root_dir, retention_days)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                _evt("retention.failed"),
                extra={"slug": slug, "error": str(exc), "days": retention_days},
            )

    return {
        "mapping": str(prepared.paths.mapping_yaml),
    }


def provision_from_vision_with_config(
    ctx: Any,
    logger: "logging.Logger",
    *,
    slug: str,
    pdf_path: Path,
    config: AssistantConfig,
    retention_days: int,
    prepared_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Esegue Vision usando una configurazione Assistant già risolta dall'orchestratore.
    """
    ensure_dotenv_loaded()

    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        raise ConfigError("Context privo di repo_root_dir per Vision onboarding.", slug=slug)
    try:
        safe_pdf = ensure_within_and_resolve(repo_root_dir, pdf_path)
    except ConfigError as exc:
        raise exc.__class__(str(exc), slug=slug, file_path=getattr(exc, "file_path", None)) from exc

    prepared = _prepare_payload(
        ctx,
        slug,
        Path(safe_pdf),
        prepared_prompt=prepared_prompt,
        config=config,
        logger=logger,
        retention_days=retention_days,
    )

    response = _invoke_assistant(prepared)
    if response.get("status") == "halt":
        raise HaltError(response.get("message_ui", "Vision insufficiente"), response.get("missing", {}))

    return _persist_outputs(
        prepared,
        response,
        logger,
        retention_days=retention_days,
    )


def provision_from_vision_yaml_with_config(
    ctx: Any,
    logger: "logging.Logger",
    *,
    slug: str,
    yaml_path: Path,
    config: AssistantConfig,
    retention_days: int,
    prepared_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Variante YAML-first di Vision che prende la configurazione già risolta.
    """
    ensure_dotenv_loaded()

    prepared = _prepare_payload_from_yaml(
        ctx,
        slug,
        yaml_path,
        prepared_prompt=prepared_prompt,
        config=config,
        logger=logger,
        retention_days=retention_days,
    )

    response = _invoke_assistant(prepared)
    if response.get("status") == "halt":
        raise HaltError(response.get("message_ui", "Vision insufficiente"), response.get("missing", {}))

    return _persist_outputs(
        prepared,
        response,
        logger,
        retention_days=retention_days,
    )


def _determine_structured_output(client: Any, assistant_id: str, strict_output: bool) -> bool:
    """Decide se usare JSON Schema: strict_output deve essere True (strict-only)."""
    _ = (client, assistant_id)  # mantenimento firma, no calls Assistants
    if strict_output is not True:
        raise ConfigError("strict_output deve essere True (strict-only)")
    return True


def _build_response_format(use_structured: bool) -> Optional[Dict[str, Any]]:
    if not use_structured:
        raise ConfigError("structured output richiesto: strict-only")
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
    invocation: Optional[Mapping[str, Any]] = None,
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

    messages: List[Dict[str, str]] = []
    if run_instructions:
        messages.append({"role": "system", "content": str(run_instructions)})

    for msg in user_messages:
        role = (msg.get("role") or "user").strip() or "user"
        messages.append({"role": role, "content": str(msg.get("content") or "")})

    metadata = {
        "assistant_id": assistant_id,
        "source": "vision",
        "use_kb": use_kb,
        "use_structured": use_structured,
    }

    try:
        resp = run_json_model(
            model=model,
            messages=messages,
            response_format=response_format,
            metadata=metadata,
            invocation=invocation,
        )
    except ConfigError:
        raise
    except Exception as exc:
        LOGGER.error(
            _evt("responses.exception"),
            extra={"assistant_id": assistant_id, "error": str(exc)},
        )
        raise ConfigError("Responses API fallita.") from exc

    return cast(Dict[str, Any], resp.data)


def _parse_json_output(text: Optional[str], assistant_id: str, *, source: str) -> Dict[str, Any]:
    if not text:
        LOGGER.error(_evt("no_output_text"), extra={"assistant_id": assistant_id, "source": source})
        raise ConfigError("Assistant run completato ma nessun testo nel messaggio di output.")

    if not isinstance(text, str):
        text = str(text)

    if "```" in text:
        raise ConfigError(
            f"Output LLM non conforme: JSON puro richiesto (assistant_id={assistant_id}, source={source})"
        )

    stripped = text.strip()
    try:
        decoder = json.JSONDecoder()
        parsed, idx = decoder.raw_decode(stripped)
        if stripped[idx:].strip():
            raise ConfigError(
                f"Output LLM non conforme: JSON puro richiesto (assistant_id={assistant_id}, source={source})"
            )
        return cast(Dict[str, Any], parsed)
    except json.JSONDecodeError as exc:
        first_line = str(exc).splitlines()[0]
        raise ConfigError(
            f"Output LLM non conforme: {first_line} (assistant_id={assistant_id}, source={source})"
        ) from exc
