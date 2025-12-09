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
from ui.config_store import get_vision_model
from ui.imports import get_streamlit


class _ProvisionFromVisionFunc(Protocol):
    def __call__(
        self,
        *,
        ctx: Any,
        logger: logging.Logger,
        slug: str,
        pdf_path: Path,
        model: str,
        prepared_prompt: Optional[str] = None,
    ) -> Dict[str, Any]: ...


class _ProvisionFromVisionYamlFunc(Protocol):
    def __call__(
        self,
        *,
        ctx: Any,
        logger: logging.Logger,
        slug: str,
        yaml_path: Path,
        model: str,
        prepared_prompt: Optional[str] = None,
    ) -> Dict[str, Any]: ...


class _PreparePromptFunc(Protocol):
    def __call__(self, *, ctx: Any, slug: str, pdf_path: Path, model: str, logger: Any) -> str: ...


class _PreparePromptYamlFunc(Protocol):
    def __call__(self, *, ctx: Any, slug: str, yaml_path: Path, model: str, logger: Any) -> str: ...


def _load_semantic_bindings() -> tuple[
    Type[Exception],
    _ProvisionFromVisionFunc,
    _PreparePromptFunc,
    Optional[_ProvisionFromVisionYamlFunc],
    Optional[_PreparePromptYamlFunc],
]:
    """Carica dinamicamente le binding da semantic.vision_provision."""
    candidates = (
        "src.semantic.vision_provision",
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
        provision_yaml = getattr(module, "provision_from_vision_yaml", None)
        prepare_yaml = getattr(module, "prepare_assistant_input_from_yaml", None)
        if isinstance(halt_error, type) and callable(provision) and callable(prepare):
            return (
                cast(Type[Exception], halt_error),
                cast(_ProvisionFromVisionFunc, provision),
                cast(_PreparePromptFunc, prepare),
                cast(Optional[_ProvisionFromVisionYamlFunc], provision_yaml) if callable(provision_yaml) else None,
                cast(Optional[_PreparePromptYamlFunc], prepare_yaml) if callable(prepare_yaml) else None,
            )
    from ...semantic.vision_provision import HaltError as fallback_error
    from ...semantic.vision_provision import prepare_assistant_input as fallback_prepare
    from ...semantic.vision_provision import provision_from_vision as fallback_provision
    from ...semantic.vision_provision import provision_from_vision_yaml as fallback_provision_yaml

    fallback_prepare_yaml: Optional[_PreparePromptYamlFunc]
    try:
        from ...semantic.vision_provision import prepare_assistant_input_from_yaml as fallback_prepare_yaml
    except Exception:
        fallback_prepare_yaml = None

    return (
        fallback_error,
        fallback_provision,
        fallback_prepare,
        cast(Optional[_ProvisionFromVisionYamlFunc], fallback_provision_yaml),
        cast(Optional[_PreparePromptYamlFunc], fallback_prepare_yaml) if callable(fallback_prepare_yaml) else None,
    )


HaltError: Type[Exception]
_provision_from_vision: _ProvisionFromVisionFunc
_prepare_prompt: _PreparePromptFunc
_provision_from_vision_yaml: Optional[_ProvisionFromVisionYamlFunc]
_prepare_prompt_yaml: Optional[_PreparePromptYamlFunc]
HaltError, _provision_from_vision, _prepare_prompt, _provision_from_vision_yaml, _prepare_prompt_yaml = (
    _load_semantic_bindings()
)


def _resolve_model(slug: str, model: Optional[str]) -> str:
    resolved = (model or get_vision_model()).strip()
    if not resolved:
        raise ConfigError("Modello Vision non configurato o vuoto.", slug=slug)
    return resolved


@dataclass(frozen=True)
class VisionArtifacts:
    """Riferimenti ai due artefatti SSoT prodotti da Vision."""

    mapping_yaml: Path
    cartelle_yaml: Path


# -----------------------------
# Utilità hash e idempotenza
# -----------------------------
def _sha256_of_file(base_dir: Path, path: Path, chunk_size: int = 8192) -> str:
    """Calcola l'hash del PDF con path-safety garantita."""
    safe_path = ensure_within_and_resolve(base_dir, path)
    h = hashlib.sha256()
    with safe_path.open("rb") as fh:
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


def _vision_yaml_path(base_dir: Path, *, pdf_path: Optional[Path] = None) -> Path:
    base = Path(base_dir)
    candidate = (
        (pdf_path.parent / "visionstatement.yaml")
        if pdf_path is not None
        else (base / "config" / "visionstatement.yaml")
    )
    resolved = ensure_within_and_resolve(base, candidate)
    return cast(Path, resolved)


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
    except Exception as exc:
        logger = get_structured_logger("ui.vision")
        logger.warning(
            "ui.vision.hash_read_failed",
            extra={"path": str(path), "error": str(exc)},
        )
        return None


def _save_hash(base_dir: Path, *, digest: str, model: str) -> None:
    from datetime import datetime, timezone

    payload = json.dumps(
        {"hash": digest, "model": model, "ts": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    safe_write_text(_hash_sentinel(base_dir), payload + "\n")


def _ensure_structured_output_and_prompt(ctx: Any, *, slug: str) -> None:
    """
    Garantisce che la run Vision usi structured output e un system prompt aggiornato.
    """
    strict_output = True
    settings = getattr(ctx, "settings", None)
    try:
        vision_settings = getattr(settings, "vision_settings", None)
        strict_output = getattr(vision_settings, "strict_output", strict_output)
    except Exception:
        strict_output = True
    if strict_output is False:
        return

    repo_root = Path(__file__).resolve().parents[3]
    prompt_path = ensure_within_and_resolve(repo_root, repo_root / "config" / "assistant_vision_system_prompt.txt")
    try:
        prompt_text = read_text_safe(repo_root, prompt_path, encoding="utf-8").strip()
    except Exception as exc:
        raise ConfigError(
            (
                "System prompt Vision mancante: aggiorna config/assistant_vision_system_prompt.txt "
                "e riallinea l'assistente."
            ),
            slug=slug,
            file_path=str(prompt_path),
        ) from exc
    if not prompt_text:
        raise ConfigError(
            (
                "System prompt Vision vuoto: aggiorna config/assistant_vision_system_prompt.txt "
                "e riallinea l'assistente."
            ),
            slug=slug,
            file_path=str(prompt_path),
        )


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
    safe_pdf = cast(Path, ensure_within_and_resolve(base_dir, pdf_path))
    if not safe_pdf.exists():
        raise ConfigError(f"PDF non trovato: {safe_pdf}", slug=slug, file_path=str(safe_pdf))
    yaml_path = _vision_yaml_path(base_dir, pdf_path=safe_pdf)
    if not yaml_path.exists():
        raise ConfigError(
            "visionstatement.yaml mancante o non leggibile: esegui prima la compilazione PDF→YAML",
            slug=slug,
            file_path=str(yaml_path),
        )

    digest = _sha256_of_file(base_dir, safe_pdf)
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

    resolved_model = _resolve_model(slug, model)

    # Esecuzione reale (delegata al layer semantic)
    try:
        provision_from_semantic_module = getattr(_provision_from_vision, "__module__", "").endswith("vision_provision")
        if _provision_from_vision_yaml is not None and provision_from_semantic_module:
            result = _provision_from_vision_yaml(
                ctx=ctx,
                logger=logger,
                slug=slug,
                yaml_path=yaml_path,
                model=resolved_model,
                prepared_prompt=prepared_prompt,
            )
        else:
            result = _provision_from_vision(
                ctx=ctx,
                logger=logger,
                slug=slug,
                pdf_path=safe_pdf,
                model=resolved_model,
                prepared_prompt=prepared_prompt,
            )
    except HaltError:
        # Propaga direttamente verso la UI per consentire un messaggio dedicato.
        raise

    # Aggiorna sentinel JSON (con log utile ai test)
    _save_hash(base_dir, digest=digest, model=resolved_model)
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
    _ensure_structured_output_and_prompt(ctx, slug=slug)
    eff_logger = logger or get_structured_logger("ui.vision.service")
    pdf_path = Path(pdf_path)
    base_dir = getattr(ctx, "base_dir", None)
    safe_pdf: Path = pdf_path
    safe_yaml: Optional[Path] = None
    if base_dir is not None:
        safe_pdf = cast(Path, ensure_within_and_resolve(base_dir, pdf_path))
        safe_yaml = _vision_yaml_path(base_dir, pdf_path=safe_pdf)
    else:
        safe_yaml = safe_pdf.parent / "visionstatement.yaml"
    if safe_yaml is not None and not safe_yaml.exists():
        raise ConfigError(
            "visionstatement.yaml mancante o non leggibile: esegui prima la compilazione PDF→YAML",
            slug=slug,
            file_path=str(safe_yaml),
        )

    prepared_prompt: Optional[str] = prepared_prompt_override
    if preview_prompt:
        st = get_streamlit()
        with st.container(border=True):
            st.subheader("Anteprima prompt inviato all’Assistant")
            st.caption("Verifica il testo generato. Premi **Prosegui** per continuare.")
            if prepared_prompt is None:
                preferred_model = model or get_vision_model()
                if _prepare_prompt_yaml is not None and safe_yaml is not None:
                    prepared_prompt = _prepare_prompt_yaml(
                        ctx=ctx,
                        slug=slug,
                        yaml_path=safe_yaml,
                        model=preferred_model,
                        logger=eff_logger,
                    )
                else:
                    prepared_prompt = _prepare_prompt(
                        ctx=ctx,
                        slug=slug,
                        pdf_path=safe_pdf,
                        # stessa sorgente del default usato in esecuzione
                        model=preferred_model,
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
