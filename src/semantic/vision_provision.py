# =========================
# File: src/semantic/vision_provision.py
# =========================
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text

# Convenzioni del repo
from pipeline.path_utils import ensure_within_and_resolve

# Ri-uso di schema e prompt dal modulo esistente (contratto unico)
# Nota: gli identificatori nel modulo vision_ai possono essere "interni" (prefisso _),
#       ma qui li importiamo esplicitamente per evitare drift tra definizioni duplicate.
from semantic.vision_ai import JSON_SCHEMA, SYSTEM_PROMPT  # noqa: E402
from semantic.vision_utils import json_to_cartelle_raw_yaml  # noqa: E402
from src.ai.client_factory import make_openai_client


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

        doc = fitz.open(pdf_path)
        texts: List[str] = []
        for page in doc:
            texts.append(page.get_text("text"))
        return "\n".join(texts).strip()
    except Exception:
        # Fallback "best effort": non blocca il flusso
        return "Snapshot non disponibile (PyMuPDF non installato o PDF non leggibile)."


def _write_audit_line(base_dir: Path, record: Dict[str, Any]) -> None:
    logs_dir = ensure_within_and_resolve(base_dir, base_dir / "logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = ensure_within_and_resolve(logs_dir, logs_dir / "vision_provision.log")
    # JSON Lines append
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class _Paths:
    base_dir: Path
    semantic_dir: Path
    vision_txt: Path
    vision_yaml: Path
    cartelle_yaml: Path


def _resolve_paths(ctx_base_dir: str) -> _Paths:
    base = Path(ctx_base_dir)
    sem_dir = ensure_within_and_resolve(base, base / "semantic")
    vision_txt = ensure_within_and_resolve(sem_dir, sem_dir / "vision_statement.txt")
    vision_yaml = ensure_within_and_resolve(sem_dir, sem_dir / "vision_statement.yaml")
    cartelle_yaml = ensure_within_and_resolve(sem_dir, sem_dir / "cartelle_raw.yaml")
    return _Paths(base, sem_dir, vision_txt, vision_yaml, cartelle_yaml)


def _create_vector_store_with_pdf(client, pdf_path: Path) -> str:
    vs = client.vector_stores.create(name="vision-kb-runtime")
    vs_id = vs.id

    up = client.files.create(file=pdf_path.open("rb"), purpose="assistants")
    client.vector_stores.files.batch(vector_store_id=vs_id, file_ids=[up.id])

    # Polling semplice per indicizzazione
    for _ in range(60):
        status = client.vector_stores.retrieve(vs_id)
        if getattr(status, "file_counts", None) and status.file_counts.completed >= 1:
            break
        time.sleep(0.5)
    return vs_id


def _validate_json_payload(data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ConfigError("Output modello non valido: payload non e un oggetto JSON.")
    if "context" not in data or "areas" not in data:
        raise ConfigError("Output modello non valido: mancano 'context' o 'areas'.")
    if not isinstance(data["areas"], list) or not data["areas"]:
        raise ConfigError("Output modello non valido: 'areas' vuoto o non list.")


def provision_from_vision(
    ctx,
    logger,
    *,
    slug: str,
    pdf_path: Path,
    model: str = "gpt-4.1-mini",
) -> Dict[str, Any]:
    """
    Esegue l'onboarding Vision:
    1) snapshot testo
    2) invocazione AI (Responses API + file_search) -> JSON schema
    3) scrittura YAML: vision_statement.yaml e cartelle_raw.yaml
    Ritorna metadati utili per UI/audit.
    """
    if not pdf_path.exists():
        raise ConfigError(f"PDF non trovato: {pdf_path}")

    paths = _resolve_paths(ctx.base_dir)
    paths.semantic_dir.mkdir(parents=True, exist_ok=True)

    pdf_hash = _sha256_of_file(pdf_path)

    # 1) Snapshot testuale
    snapshot = _extract_pdf_text(pdf_path)
    safe_write_text(paths.vision_txt, snapshot)

    # 2) Invocazione AI
    client = make_openai_client()
    vs_id = _create_vector_store_with_pdf(client, pdf_path)

    user_block = (
        "Contesto cliente:\n"
        f"- slug: {slug}\n"
        f"- client_name: {slug}\n"
        "\nVision Statement: vedi documento allegato nel contesto (tool file_search)."
    )

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},  # riuso dal modulo esistente
            {"role": "user", "content": user_block},
        ],
        tools=[{"type": "file_search", "file_search": {"vector_store_ids": [vs_id]}}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "vision_semantic_mapping", "schema": JSON_SCHEMA},
        },
        temperature=0.2,
    )

    data: Dict[str, Any] = resp.output_parsed  # JSON validato lato API
    _validate_json_payload(data)

    # 3) JSON -> YAML (vision + cartelle_raw)
    vision_yaml_str = yaml.safe_dump(
        {
            "context": data["context"],
            **{
                area["key"]: {
                    "ambito": area["ambito"],
                    "descrizione": area["descrizione"],
                    "esempio": area["esempio"],
                }
                for area in data["areas"]
            },
            **({"synonyms": data.get("synonyms")} if data.get("synonyms") else {}),
        },
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )
    safe_write_text(paths.vision_yaml, vision_yaml_str)

    cartelle_yaml_str = json_to_cartelle_raw_yaml(data, slug=slug)
    safe_write_text(paths.cartelle_yaml, cartelle_yaml_str)

    # Audit
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "pdf": str(pdf_path),
        "pdf_hash": pdf_hash,
        "model": model,
        "yaml_paths": {"vision": str(paths.vision_yaml), "cartelle_raw": str(paths.cartelle_yaml)},
        "areas_count": len(data["areas"]),
    }
    _write_audit_line(paths.base_dir, record)
    logger.info("vision_provision: completato", extra=record)

    return {
        "pdf_hash": pdf_hash,
        "yaml_paths": {"vision": str(paths.vision_yaml), "cartelle_raw": str(paths.cartelle_yaml)},
        "model": model,
        "generated_at": record["ts"],
        "areas_count": len(data["areas"]),
    }
