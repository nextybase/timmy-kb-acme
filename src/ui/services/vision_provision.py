# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/services/vision_provision.py
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Type, cast

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.imports import get_streamlit


class _ProvisionFromVisionFunc(Protocol):
    def __call__(
        self,
        *,
        ctx: Any,
        logger: logging.Logger,
        slug: str,
        pdf_path: Path,
        force: bool = False,
        model: Optional[str] = None,
        prepared_prompt: Optional[str] = None,
    ) -> Dict[str, Any]: ...


class _PreparePromptFunc(Protocol):
    def __call__(self, *, ctx: Any, slug: str, pdf_path: Path, model: str, logger: Any) -> str: ...


def _load_semantic_bindings() -> tuple[Type[Exception], _ProvisionFromVisionFunc, _PreparePromptFunc]:
    """Carica dinamicamente le binding da semantic.vision_provision."""
    candidates = (
        "src.semantic.vision_provision",
        "timmykb.semantic.vision_provision",
        "semantic.vision_provision",
    )
    for module_name in candidates:
        try:
            module = import_module(module_name)
        except ImportError:
            continue
        halt_error = getattr(module, "HaltError", None)
        provision = getattr(module, "provision_from_vision", None)
        prepare = getattr(module, "prepare_assistant_input", None)
        if isinstance(halt_error, type) and callable(provision) and callable(prepare):
            return (
                cast(Type[Exception], halt_error),
                cast(_ProvisionFromVisionFunc, provision),
                cast(_PreparePromptFunc, prepare),
            )
    from ...semantic.vision_provision import HaltError as fallback_error
    from ...semantic.vision_provision import prepare_assistant_input as fallback_prepare
    from ...semantic.vision_provision import provision_from_vision as fallback_provision

    return fallback_error, fallback_provision, fallback_prepare


HaltError: Type[Exception]
_provision_from_vision: _ProvisionFromVisionFunc
_prepare_prompt: _PreparePromptFunc
HaltError, _provision_from_vision, _prepare_prompt = _load_semantic_bindings()


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
    sdir = ensure_within_and_resolve(base_dir, base_dir / "semantic")
    return cast(Path, sdir)


def _hash_sentinel(base_dir: Path) -> Path:
    # Sentinel contrattuale dei test: .vision_hash (formato JSON)
    path = ensure_within_and_resolve(_semantic_dir(base_dir), _semantic_dir(base_dir) / ".vision_hash")
    return cast(Path, path)


def _artifacts_paths(base_dir: Path) -> VisionArtifacts:
    sdir = _semantic_dir(base_dir)
    mapping = ensure_within_and_resolve(sdir, sdir / "semantic_mapping.yaml")
    cartelle = ensure_within_and_resolve(sdir, sdir / "cartelle_raw.yaml")
    return VisionArtifacts(mapping_yaml=cast(Path, mapping), cartelle_yaml=cast(Path, cartelle))


def _artifacts_exist(base_dir: Path) -> bool:
    art = _artifacts_paths(base_dir)
    return art.mapping_yaml.exists() and art.cartelle_yaml.exists()


def _load_last_hash(base_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Legge il sentinel JSON se presente.
    Ritorna un dict con almeno {"hash": str, "model": str, "ts": str} oppure None.
    """
    path = _hash_sentinel(base_dir)
    if not path.exists():
        return None
    try:
        raw = cast(str, read_text_safe(base_dir, path, encoding="utf-8"))
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_hash(base_dir: Path, *, digest: str, model: str) -> None:
    from datetime import datetime, timezone

    payload = json.dumps(
        {"hash": digest, "model": model, "ts": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    safe_write_text(_hash_sentinel(base_dir), payload + "\n")


# -----------------------------
# API principale (bridge UI)
# -----------------------------
def provision_from_vision(
    ctx: Any,
    logger: logging.Logger,
    *,
    slug: str,
    pdf_path: str | Path,
    force: bool = False,
    model: Optional[str] = None,
    prepared_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Esegue Vision in modo idempotente lato UI:
    - calcola hash del PDF,
    - se non 'force' e hash invariato con artefatti già presenti → BLOCCA con ConfigError,
    - altrimenti invoca semantic.provision_from_vision e aggiorna sentinel JSON.

    Ritorna:
        {
          "skipped": bool,
          "hash": "<sha256>",
          "mapping": "<abs path>",
          "cartelle_raw": "<abs path>"
        }
    """
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)

    # Path sicuri entro il workspace
    pdf_path = Path(pdf_path)
    safe_pdf = ensure_within_and_resolve(base_dir, pdf_path)
    safe_pdf = cast(Path, safe_pdf)
    if not safe_pdf.exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))

    digest = _sha256_of_file(safe_pdf)
    last = _load_last_hash(base_dir)
    last_digest = (last or {}).get("hash")

    # Box artefatti
    art = _artifacts_paths(base_dir)

    # GATE: se PDF invariato e artefatti presenti → richiedi 'force'
    gate_hit = (last_digest == digest) and art.mapping_yaml.exists() and art.cartelle_yaml.exists()
    logger.info("ui.vision.gate", extra={"slug": slug, "hit": gate_hit})
    if gate_hit and not force:
        # Blocco esplicito richiesto dai test (“then force”)
        raise ConfigError(
            "Vision già eseguito per questo PDF. Usa la modalità 'Forza rigenerazione' per procedere.",
            slug=slug,
            file_path=str(_hash_sentinel(base_dir)),
        )

    # Esecuzione reale (delegata al layer semantic)
    try:
        result = _provision_from_vision(
            ctx=ctx,
            logger=logger,
            slug=slug,
            pdf_path=safe_pdf,
            model=model or "gpt-4.1-mini",
            force=force,
            prepared_prompt=prepared_prompt,
        )
    except HaltError:
        # Propaga direttamente verso la UI per consentire un messaggio dedicato.
        raise

    # Aggiorna sentinel JSON (con log utile ai test)
    _save_hash(base_dir, digest=digest, model=model or "gpt-4.1-mini")
    logger.info("ui.vision.update_hash", extra={"slug": slug, "file_path": str(_hash_sentinel(base_dir))})

    # Ritorno coerente con la firma documentata
    return {
        "skipped": False,
        "hash": digest,
        "mapping": cast(str, result.get("mapping", "")),
        "cartelle_raw": cast(str, result.get("cartelle_raw", "")),
    }


def run_vision(
    ctx: Any,
    *,
    slug: str,
    pdf_path: Path,
    force: bool = False,
    model: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    preview_prompt: bool = False,
    prepared_prompt_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wrapper semplificato per la UI: esegue Vision con logger di default.
    Se `preview_prompt` è True mostra il prompt generato prima di inviare la richiesta.
    """
    eff_logger = logger or get_structured_logger("ui.vision.service")
    pdf_path = Path(pdf_path)
    base_dir = getattr(ctx, "base_dir", None)
    safe_pdf: Path = pdf_path
    if base_dir is not None:
        safe_pdf = cast(Path, ensure_within_and_resolve(base_dir, pdf_path))

    prepared_prompt: Optional[str] = prepared_prompt_override
    if preview_prompt:
        st = get_streamlit()
        with st.container(border=True):
            st.subheader("Anteprima prompt inviato all’Assistant")
            st.caption("Verifica il testo generato. Premi **Prosegui** per continuare.")
            if prepared_prompt is None:
                prepared_prompt = _prepare_prompt(
                    ctx=ctx,
                    slug=slug,
                    pdf_path=safe_pdf,
                    model=model or "gpt-4.1-mini",
                    logger=eff_logger,
                )
            st.text_area("Prompt", value=prepared_prompt, height=420, disabled=True)
            proceed = st.button("Prosegui", type="primary")
            if not proceed:
                st.stop()

    return provision_from_vision(
        ctx=ctx,
        logger=eff_logger,
        slug=slug,
        pdf_path=safe_pdf,
        force=force,
        model=model,
        prepared_prompt=prepared_prompt,
    )
