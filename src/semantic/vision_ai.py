# src/semantic/vision_ai.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ai.client_factory import make_openai_client
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve
from semantic.vision_utils import json_to_cartelle_raw_yaml  # factory centralizzato

_MODEL = "gpt-4.1-mini"
_MAX_VISION_CHARS = 200_000
_TEXT_SNAPSHOT_NAME = "vision_statement.txt"

JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "vision_semantic_mapping",
    "type": "object",
    "required": ["context", "areas"],
    "properties": {
        "context": {
            "type": "object",
            "required": ["slug", "client_name"],
            "properties": {
                "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
                "client_name": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "areas": {
            "type": "array",
            "minItems": 3,
            "items": {
                "type": "object",
                "required": ["key", "ambito", "descrizione", "esempio"],
                "properties": {
                    "key": {"type": "string", "pattern": "^[a-z0-9-]+$"},
                    "ambito": {"type": "string"},
                    "descrizione": {"type": "string", "maxLength": 240},
                    "esempio": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        },
        "synonyms": {
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
        },
    },
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "RUOLO: Assistente per knowledge management. Estrai una tassonomia dal Vision Statement.\n"
    "OBIETTIVO: Restituisci SOLO un JSON conforme allo schema. Niente testo extra.\n"
    "REGOLE:\n"
    "- Italiano professionale. Chiavi in slug (lowercase, trattini).\n"
    "- Descrizioni: 1 frase breve (<= 20 parole). Esempio: elenco tipologie documentali concrete.\n"
    "- Inserisci `synonyms` solo se utile (es. 'pa': ['pubblica amministrazione']).\n"
    "VALIDAZIONE: Lo schema e' vincolante; se i dati mancano, ometti aree non supportate."
)


def _resolve_optional(base: Path, candidate: Path | str) -> Optional[Path]:
    candidate_path = Path(base) / Path(candidate)
    try:
        return ensure_within_and_resolve(base, candidate_path)
    except ConfigError:
        return None


def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise ConfigError("Impossibile aprire il VisionStatement.pdf: PyMuPDF non installato.") from exc
    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        raise ConfigError("Impossibile aprire il VisionStatement.pdf") from exc
    try:
        chunks: list[str] = []
        total = 0
        for page in document:
            page_text = page.get_text("text").strip()
            if not page_text:
                continue
            chunks.append(page_text)
            total += len(page_text)
            if total >= _MAX_VISION_CHARS:
                break
        if not chunks:
            raise ConfigError("Il VisionStatement.pdf non contiene testo estraibile.")
        combined = "\n\n".join(chunks)
        return combined[:_MAX_VISION_CHARS]
    finally:
        document.close()


@dataclass(frozen=True)
class VisionPaths:
    base_dir: Path
    config_pdf_client: Optional[Path]
    raw_pdf: Path
    vision_yaml: Path
    cartelle_yaml: Path
    config_pdf_repo: Path
    text_snapshot: Path


def _resolve_paths(ctx: ClientContext, slug: str) -> VisionPaths:
    base = Path(ctx.base_dir)  # output/timmy-kb-<slug>
    config_pdf_client = _resolve_optional(base, Path("config") / "VisionStatement.pdf")
    raw_pdf = ensure_within_and_resolve(base, base / "raw" / "VisionStatement.pdf")
    vision_yaml = ensure_within_and_resolve(base, base / "semantic" / "vision_statement.yaml")
    cartelle_yaml = ensure_within_and_resolve(base, base / "semantic" / "cartelle_raw.yaml")
    text_snapshot = ensure_within_and_resolve(base, base / "semantic" / _TEXT_SNAPSHOT_NAME)
    project_root = Path(__file__).resolve().parents[2]
    config_pdf_repo = ensure_within_and_resolve(project_root, project_root / "config" / "VisionStatement.pdf")
    return VisionPaths(base, config_pdf_client, raw_pdf, vision_yaml, cartelle_yaml, config_pdf_repo, text_snapshot)


def _pick_pdf(p: VisionPaths) -> Path:
    if p.config_pdf_client and p.config_pdf_client.exists():
        return p.config_pdf_client
    if p.raw_pdf.exists():
        return p.raw_pdf
    if p.config_pdf_repo.exists():
        return p.config_pdf_repo
    client_config_path = p.base_dir / "config" / "VisionStatement.pdf"
    client_raw_path = p.base_dir / "raw" / "VisionStatement.pdf"
    raise ConfigError(
        f"VisionStatement.pdf non trovato in {client_config_path} ne' in {client_raw_path} "
        f"ne' nel repository globale {p.config_pdf_repo}. Carica il PDF in config/ o raw/ e riprova."
    )


def _json_to_yaml(data: Dict[str, Any]) -> str:
    try:
        context = data["context"]
        areas = data["areas"]
    except KeyError as exc:
        raise ConfigError(f"Vision AI: campo obbligatorio assente nel JSON: {exc}") from exc
    if not isinstance(areas, list) or not areas:
        raise ConfigError("Vision AI: campo 'areas' vuoto o non valido.")
    mapping: Dict[str, Dict[str, Any]] = {}
    for area in areas:
        if not isinstance(area, dict):
            raise ConfigError("Vision AI: elemento di 'areas' non e' un oggetto JSON.")
        try:
            key = area["key"]
            mapping[key] = {
                "ambito": area["ambito"],
                "descrizione": area["descrizione"],
                "esempio": area["esempio"],
            }
        except KeyError as exc:
            raise ConfigError(f"Vision AI: area incompleta ({exc}).") from exc
    yaml_obj: Dict[str, Any] = {"context": context, **mapping}
    synonyms = data.get("synonyms")
    if synonyms:
        yaml_obj["synonyms"] = synonyms
    return yaml.safe_dump(yaml_obj, allow_unicode=True, sort_keys=False, width=100)


def _message_content_to_text(message_content: Any) -> str:
    if not message_content:
        return ""
    if isinstance(message_content, str):
        return message_content.strip()
    text_parts: list[str] = []
    for part in message_content:
        if isinstance(part, dict):
            text = part.get("text") or ""
        else:
            text = getattr(part, "text", "") or ""
        if text:
            text_parts.append(str(text))
    return "".join(text_parts).strip()


def generate_pair(ctx: ClientContext, logger, *, slug: str, model: str = _MODEL) -> Dict[str, str]:
    """Genera vision_statement.yaml e cartelle_raw.yaml e restituisce i path."""
    paths = _resolve_paths(ctx, slug)
    pdf_path = _pick_pdf(paths)

    client = make_openai_client()

    pdf_text = _extract_pdf_text(pdf_path)
    safe_write_text(paths.text_snapshot, pdf_text)
    logger.info(
        "vision_ai.text_dump",
        extra={"slug": slug, "chars": len(pdf_text), "path": str(paths.text_snapshot)},
    )

    client_name = ctx.client_name or (ctx.settings or {}).get("client_name") or slug
    user_block = (
        "Contesto cliente:\n"
        f"- slug: {slug}\n"
        f"- client_name: {client_name}\n"
        "\nVision Statement: testo estratto dal PDF (troncato a 200k caratteri)."
    )
    user_prompt = f"{user_block}\n\nVision Statement (testo estratto):\n{pdf_text}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "vision_semantic_mapping", "schema": JSON_SCHEMA},
            },
            temperature=0.1,
            max_completion_tokens=2000,
        )
    except Exception as exc:
        raise ConfigError(f"Vision AI: chiamata API fallita: {exc}") from exc

    if not response.choices:
        raise ConfigError("Vision AI: nessuna scelta restituita dal modello.")
    choice = response.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise ConfigError("Vision AI: completamento interrotto per lunghezza (finish_reason=length).")
    message = getattr(choice, "message", None)
    if message is None:
        raise ConfigError("Vision AI: risposta priva del messaggio atteso.")
    if getattr(message, "refusal", None):
        raise ConfigError("Vision AI: il modello ha rifiutato di rispondere.")
    parsed = _message_content_to_text(getattr(message, "content", ""))
    if not parsed:
        logger.error(
            "vision_ai.responses_empty",
            extra={"slug": slug, "finish_reason": getattr(choice, "finish_reason", None)},
        )
        raise ConfigError("Vision AI: risposta priva di contenuto testuale.")

    try:
        data = json.loads(parsed)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Vision AI: risposta non JSON: {exc}") from exc

    if "context" not in data or "areas" not in data:
        raise ConfigError("Vision AI: risposta incompleta (mancano 'context' o 'areas').")

    vision_yaml_str = _json_to_yaml(data)
    safe_write_text(paths.vision_yaml, vision_yaml_str)

    cartelle_yaml_str = json_to_cartelle_raw_yaml(data, slug)
    safe_write_text(paths.cartelle_yaml, cartelle_yaml_str)

    usage = getattr(response, "usage", None)
    logger.info(
        "vision_ai.generate_pair.done",
        extra={
            "slug": slug,
            "vision_yaml": str(paths.vision_yaml),
            "cartelle_raw_yaml": str(paths.cartelle_yaml),
            "model": model,
            "tokens_prompt": getattr(usage, "prompt_tokens", None),
            "tokens_completion": getattr(usage, "completion_tokens", None),
        },
    )

    return {
        "vision_yaml": str(paths.vision_yaml),
        "cartelle_raw_yaml": str(paths.cartelle_yaml),
        "model": model,
        "tokens_prompt": getattr(usage, "prompt_tokens", None),
        "tokens_completion": getattr(usage, "completion_tokens", None),
    }


def generate(ctx: ClientContext, logger, *, slug: str) -> str:
    """
    Genera 'semantic/vision_statement.yaml' dal VisionStatement.pdf del cliente.
    Ritorna il path del file YAML generato (stringa).
    """
    result = generate_pair(ctx, logger, slug=slug, model=_MODEL)
    logger.info(
        "vision_ai.generate.done",
        extra={
            "slug": slug,
            "out": result["vision_yaml"],
            "tokens_prompt": result.get("tokens_prompt"),
            "tokens_completion": result.get("tokens_completion"),
        },
    )
    return result["vision_yaml"]
