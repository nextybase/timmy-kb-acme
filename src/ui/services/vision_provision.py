# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/services/vision_provision.py
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, cast

from ai.types import AssistantConfig
from ai.vision_config import resolve_vision_config
from ai.vision_config import resolve_vision_retention_days as _resolve_vision_retention_days
from pipeline.capabilities.vision import load_vision_bindings
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.vision_runner import run_vision_with_gating
from ui.imports import get_streamlit


class _ProvisionFromVisionWithConfigFunc(Protocol):
    def __call__(
        self,
        *,
        ctx: Any,
        logger: logging.Logger,
        slug: str,
        pdf_path: Path,
        config: AssistantConfig,
        retention_days: int,
        prepared_prompt: Optional[str] = None,
    ) -> Dict[str, Any]: ...


class _ProvisionFromVisionYamlWithConfigFunc(Protocol):
    def __call__(
        self,
        *,
        ctx: Any,
        logger: logging.Logger,
        slug: str,
        yaml_path: Path,
        config: AssistantConfig,
        retention_days: int,
        prepared_prompt: Optional[str] = None,
    ) -> Dict[str, Any]: ...


class _PreparePromptFunc(Protocol):
    def __call__(self, *, ctx: Any, slug: str, pdf_path: Path, model: str, logger: Any) -> str: ...


class _PreparePromptYamlFunc(Protocol):
    def __call__(self, *, ctx: Any, slug: str, yaml_path: Path, model: str, logger: Any) -> str: ...


VISION_BINDINGS = load_vision_bindings()

HaltError = VISION_BINDINGS.halt_error
_provision_from_vision_with_config = VISION_BINDINGS.provision_with_config
_prepare_prompt = VISION_BINDINGS.prepare_with_config
_provision_from_vision_yaml_with_config = VISION_BINDINGS.provision_yaml_with_config
_prepare_prompt_yaml = VISION_BINDINGS.prepare_yaml_with_config


@dataclass(frozen=True)
class VisionArtifacts:
    """Riferimenti all'artefatto SSoT prodotto da Vision."""

    mapping_yaml: Path


def resolve_vision_retention_days(ctx: Any) -> int:
    """Forward SSoT per il retention dei file Vision lato UI."""
    return _resolve_vision_retention_days(ctx)


# -----------------------------
# Utilità hash e idempotenza
# -----------------------------
def _sha256_of_file(perimeter_root: Path, path: Path, chunk_size: int = 8192) -> str:
    """Calcola l'hash del PDF con path-safety garantita."""
    safe_path = ensure_within_and_resolve(perimeter_root, path)
    h = hashlib.sha256()
    with safe_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _semantic_dir(repo_root_dir: Path) -> Path:
    perimeter_root = repo_root_dir
    sdir = ensure_within_and_resolve(perimeter_root, repo_root_dir / "semantic")
    return cast(Path, sdir)


def _hash_sentinel(repo_root_dir: Path) -> Path:
    # Sentinel contrattuale dei test: .vision_hash (formato JSON)
    semantic_dir = _semantic_dir(repo_root_dir)
    path = ensure_within_and_resolve(semantic_dir, semantic_dir / ".vision_hash")
    return cast(Path, path)


def _artifacts_paths(repo_root_dir: Path) -> VisionArtifacts:
    sdir = _semantic_dir(repo_root_dir)
    mapping = ensure_within_and_resolve(sdir, sdir / "semantic_mapping.yaml")
    return VisionArtifacts(mapping_yaml=cast(Path, mapping))


def _artifacts_exist(repo_root_dir: Path) -> bool:
    art = _artifacts_paths(repo_root_dir)
    return art.mapping_yaml.exists()


def _load_last_hash(repo_root_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Legge il sentinel JSON se presente.
    Ritorna un dict con almeno {"hash": str, "model": str, "ts": str} oppure None.
    """
    path = _hash_sentinel(repo_root_dir)
    if not path.exists():
        return None
    try:
        raw = cast(str, read_text_safe(repo_root_dir, path, encoding="utf-8"))
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger = get_structured_logger("ui.vision")
        logger.warning(
            "ui.vision.hash_read_failed",
            extra={"path": str(path), "error": str(exc)},
        )
        return None


def _save_hash(repo_root_dir: Path, *, digest: str, model: str) -> None:
    from datetime import datetime, timezone

    payload = json.dumps(
        {"hash": digest, "model": model, "ts": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    safe_write_text(_hash_sentinel(repo_root_dir), payload + "\n")


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
def provision_from_vision_with_config(
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
          "mapping": "<abs path>"
        }
    """
    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        raise ConfigError(
            "Beta strict richiede ctx.repo_root_dir; vietata inferenza da input path. "
            "Fornire workspace root/slug/cx canonico.",
            slug=slug,
        )
    pdf_path = Path(pdf_path)
    return run_vision_with_gating(
        ctx,
        logger,
        slug=slug,
        pdf_path=pdf_path,
        force=force,
        model=model,
        prepared_prompt=prepared_prompt,
    )


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
    repo_root_dir = getattr(ctx, "repo_root_dir", None)
    if not repo_root_dir:
        raise ConfigError(
            "Beta strict richiede ctx.repo_root_dir; vietata inferenza da input path. "
            "Fornire workspace root/slug/cx canonico.",
            slug=slug,
        )
    safe_pdf = cast(Path, ensure_within_and_resolve(repo_root_dir, pdf_path))
    safe_yaml = ensure_within_and_resolve(repo_root_dir, vision_yaml_workspace_path(repo_root_dir, pdf_path=safe_pdf))
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
            st.subheader("Anteprima prompt inviato all'Assistant")
            st.caption("Verifica il testo generato. Premi **Prosegui** per continuare.")
            if prepared_prompt is None:
                preferred_config = resolve_vision_config(ctx, override_model=model)
                if _prepare_prompt_yaml is not None and safe_yaml is not None:
                    prepared_prompt = _prepare_prompt_yaml(
                        ctx=ctx,
                        slug=slug,
                        yaml_path=safe_yaml,
                        config=preferred_config,
                        logger=eff_logger,
                    )
                else:
                    prepared_prompt = _prepare_prompt(
                        ctx=ctx,
                        slug=slug,
                        pdf_path=safe_pdf,
                        # stessa sorgente del default usato in esecuzione
                        config=preferred_config,
                        logger=eff_logger,
                    )
            st.text_area("Prompt", value=prepared_prompt, height=420, disabled=True)
            proceed = st.button("Prosegui", type="primary")
            if not proceed:
                st.stop()

    return provision_from_vision_with_config(
        ctx=ctx,
        logger=eff_logger,
        slug=slug,
        pdf_path=safe_pdf,
        force=force,
        model=model,
        prepared_prompt=prepared_prompt,
    )
