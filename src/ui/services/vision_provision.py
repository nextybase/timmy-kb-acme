# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/services/vision_provision.py
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

# Nota: import "late-binding" per evitare problemi di import cycle in Streamlit.
# Espongo il nome _provision_from_vision perché i test lo monkeypatchano direttamente.
try:
    from src.semantic.vision_provision import provision_from_vision as _provision_from_vision  # type: ignore
except Exception:  # pragma: no cover
    from semantic.vision_provision import provision_from_vision as _provision_from_vision  # type: ignore


@dataclass(frozen=True)
class VisionArtifacts:
    """Riferimenti ai due artefatti SSoT prodotti da Vision."""

    mapping_yaml: Path
    cartelle_yaml: Path


# -----------------------------
# Utilità hash e idempotenza
# -----------------------------
def _sha256_of_file(path: Path, chunk_size: int = 8192) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _semantic_dir(base_dir: Path) -> Path:
    return ensure_within_and_resolve(base_dir, base_dir / "semantic")


def _sentinel_primary(base_dir: Path) -> Path:
    """Sentinel canonico usato dai test: .vision_hash (JSON)."""
    sdir = _semantic_dir(base_dir)
    return ensure_within_and_resolve(sdir, sdir / ".vision_hash")


def _sentinel_legacy(base_dir: Path) -> Path:
    """Sentinel legacy mantenuto per retro-compat: .vision_pdf.sha256 (testo)."""
    sdir = _semantic_dir(base_dir)
    return ensure_within_and_resolve(sdir, sdir / ".vision_pdf.sha256")


def _artifacts_paths(base_dir: Path) -> VisionArtifacts:
    sdir = _semantic_dir(base_dir)
    return VisionArtifacts(
        mapping_yaml=ensure_within_and_resolve(sdir, sdir / "semantic_mapping.yaml"),
        cartelle_yaml=ensure_within_and_resolve(sdir, sdir / "cartelle_raw.yaml"),
    )


def _artifacts_exist(base_dir: Path) -> bool:
    art = _artifacts_paths(base_dir)
    return art.mapping_yaml.exists() and art.cartelle_yaml.exists()


def _load_last_hash(base_dir: Path) -> Optional[str]:
    """
    Legge il sentinel; preferisce .vision_hash (JSON), fallback su .vision_pdf.sha256 (testo).
    Ritorna SEMPRE il digest (str) oppure None.
    """
    # 1) prova JSON
    p_json = _sentinel_primary(base_dir)
    if p_json.exists():
        try:
            raw = read_text_safe(base_dir, p_json, encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                h = data.get("hash") or data.get("sha256")
                if isinstance(h, str) and h.strip():
                    return h.strip()
        except Exception:
            # se corrotto, ignora e prova il legacy
            pass

    # 2) fallback: testo semplice
    p_legacy = _sentinel_legacy(base_dir)
    if p_legacy.exists():
        try:
            raw = read_text_safe(base_dir, p_legacy, encoding="utf-8").strip()
            return raw or None
        except Exception:
            return None

    return None


def _save_hash(
    base_dir: Path, *, digest: str, slug: str, mapping: str, cartelle_raw: str, model: Optional[str]
) -> None:
    """
    Scrive il sentinel JSON (.vision_hash) e quello legacy (.vision_pdf.sha256).
    Il JSON include: hash, slug, mapping, cartelle_raw, model (se noto), ts, version.
    """
    ts = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": 1,
        "ts": ts,
        "hash": digest,
        "slug": slug,
        "mapping": mapping,
        "cartelle_raw": cartelle_raw,
    }
    if model:
        payload["model"] = model

    primary = _sentinel_primary(base_dir)
    legacy = _sentinel_legacy(base_dir)

    # JSON “canonico”
    safe_write_text(primary, json.dumps(payload, ensure_ascii=False) + "\n")
    # Legacy (solo digest in chiaro)
    try:
        safe_write_text(legacy, f"{digest}\n")
    except Exception:
        # Il sentinel legacy è opzionale
        pass


def _normalize_core_result(res: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizza il risultato del core (semantic) in un formato coerente per la UI:
    - il core restituisce {"mapping": "...", "cartelle_raw": "..."}
    - la UI può aspettarsi {"yaml_paths": {...}}
    Ritorniamo ENTRAMBI (retro-compat sicura).
    """
    mapping = str(res.get("mapping", "")) if res else ""
    cartelle = str(res.get("cartelle_raw", "")) if res else ""
    out: Dict[str, Any] = {
        "mapping": mapping,
        "cartelle_raw": cartelle,
        "yaml_paths": {
            "mapping": mapping,
            "cartelle_raw": cartelle,
        },
    }
    return out


# -----------------------------
# API principale (bridge UI)
# -----------------------------
def run_vision_if_needed(
    *,
    ctx: Any,
    slug: str,
    pdf_path: str | Path,
    logger: logging.Logger,
    force: bool = False,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Esegue Vision in modo idempotente:
    - calcola hash del PDF
    - se non 'force' e hash invariato con artefatti già presenti → SKIP
    - se non 'force' e hash invariato MA artefatti mancanti → BLOCCO (ConfigError, richiede force)
    - altrimenti invoca semantic.provision_from_vision e aggiorna sentinel hash

    Output:
        {
          "skipped": bool,
          "hash": "<sha256>",
          "mapping": "<path/to/semantic_mapping.yaml>",
          "cartelle_raw": "<path/to/cartelle_raw.yaml>",
          "yaml_paths": { "mapping": "...", "cartelle_raw": "..." }
        }
    """
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)

    # Path sicuri entro il workspace
    pdf_path = Path(pdf_path)
    safe_pdf = ensure_within_and_resolve(base_dir, pdf_path)
    if not safe_pdf.exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))

    digest = _sha256_of_file(safe_pdf)
    last_digest = _load_last_hash(base_dir)

    # Caso: hash invariato
    if last_digest and last_digest == digest and not force:
        if _artifacts_exist(base_dir):
            # Telemetria: gating attivato e skip
            try:
                logger.info("ui.vision.gate", extra={"slug": slug, "hit": True, "reason": "idempotent_skip"})
            except Exception:
                pass

            art = _artifacts_paths(base_dir)
            norm = _normalize_core_result({"mapping": str(art.mapping_yaml), "cartelle_raw": str(art.cartelle_yaml)})

            # Sentinel JSON aggiornato (idempotente)
            primary = _sentinel_primary(base_dir)
            _save_hash(
                base_dir,
                digest=digest,
                slug=slug,
                mapping=norm["mapping"],
                cartelle_raw=norm["cartelle_raw"],
                model=model,
            )
            try:
                logger.info(
                    "ui.vision.update_hash",
                    extra={
                        "slug": slug,
                        "hash": digest,
                        "mapping": norm["mapping"],
                        "cartelle_raw": norm["cartelle_raw"],
                        "model": model,
                        "file_path": str(primary),
                    },
                )
            except Exception:
                pass

            return {
                "skipped": True,
                "hash": digest,
                **norm,
            }
        else:
            # Telemetria: gating attivato ma artefatti mancanti → blocco
            try:
                logger.info("ui.vision.gate", extra={"slug": slug, "hit": True, "reason": "artifacts_missing"})
            except Exception:
                pass
            raise ConfigError(
                "Vision bloccato: hash PDF invariato ma artefatti mancanti. " "Usa 'force=True' per ricostruire.",
                slug=slug,
                file_path=str(_sentinel_primary(base_dir)),
            )

    # Telemetria: gating non attivato (si procede al core)
    try:
        logger.info("ui.vision.gate", extra={"slug": slug, "hit": False})
    except Exception:
        pass

    # Esecuzione reale (delegata al core)
    core_res = _provision_from_vision(
        ctx=ctx,
        logger=logger,
        slug=slug,
        pdf_path=safe_pdf,
        model=model or "gpt-4.1-mini",
        force=force,
    )

    # Risultato coerente con la firma documentata + compat UI
    norm = _normalize_core_result(core_res or {})

    # Sentinel aggiornato (JSON + legacy)
    primary = _sentinel_primary(base_dir)
    _save_hash(
        base_dir,
        digest=digest,
        slug=slug,
        mapping=norm["mapping"],
        cartelle_raw=norm["cartelle_raw"],
        model=model,
    )
    try:
        logger.info(
            "ui.vision.update_hash",
            extra={
                "slug": slug,
                "hash": digest,
                "mapping": norm["mapping"],
                "cartelle_raw": norm["cartelle_raw"],
                "model": model,
                "file_path": str(primary),
            },
        )
    except Exception:
        pass

    return {
        "skipped": False,
        "hash": digest,
        **norm,
    }


def provision_from_vision(
    ctx: Any,
    logger: Any,
    *,
    slug: str,
    pdf_path: Path | str,
    model: Optional[str] = None,
    force: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Facade leggero per la UI (usato/monkeypatchato nei test):
    - delega al core semantic.provision_from_vision (_provision_from_vision)
    - normalizza SEMPRE includendo "yaml_paths" accanto ai campi flat.
    - SCRIVE il sentinel .vision_hash (JSON) + legacy, anche qui.
    - Logga 'ui.vision.gate' con hit=False e 'ui.vision.update_hash' includendo file_path.
    """
    if isinstance(pdf_path, str):
        pdf_path = Path(pdf_path)

    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)

    # Path sicuri e digest per sentinel
    safe_pdf = ensure_within_and_resolve(base_dir, pdf_path)
    if not safe_pdf.exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))
    digest = _sha256_of_file(safe_pdf)

    # Telemetria: questo wrapper non applica gating → hit=False
    try:
        logger.info("ui.vision.gate", extra={"slug": slug, "hit": False})
    except Exception:
        pass

    # Delega al core (o allo stub nei test)
    res = _provision_from_vision(
        ctx=ctx,
        logger=logger,
        slug=slug,
        pdf_path=safe_pdf,
        model=model or "gpt-4.1-mini",
        force=force,
        **kwargs,
    )

    # Normalizza prima, così abbiamo i path per il sentinel
    norm = _normalize_core_result(res or {})

    # Scrivi sentinel JSON + legacy (atteso dai test)
    primary = _sentinel_primary(base_dir)
    _save_hash(
        base_dir,
        digest=digest,
        slug=slug,
        mapping=norm["mapping"],
        cartelle_raw=norm["cartelle_raw"],
        model=model,
    )
    try:
        logger.info(
            "ui.vision.update_hash",
            extra={
                "slug": slug,
                "hash": digest,
                "mapping": norm["mapping"],
                "cartelle_raw": norm["cartelle_raw"],
                "model": model,
                "file_path": str(primary),
            },
        )
    except Exception:
        pass

    return norm


__all__ = [
    "run_vision_if_needed",
    "provision_from_vision",
    "_provision_from_vision",  # esposto perché i test lo monkeypatchano
    "VisionArtifacts",
]
