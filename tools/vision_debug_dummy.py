# SPDX-License-Identifier: GPL-3.0-only
# tools/vision_debug_dummy.py
from __future__ import annotations

import json
import logging
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

# --- bootstrap sys.path come negli altri tool (es. test_prototimmy) ----------------
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(REPO_ROOT))

# Import interni (dopo sys.path)
from pipeline.env_utils import ensure_dotenv_loaded  # type: ignore[import]
from pipeline.exceptions import ConfigError  # type: ignore[import]
from semantic.vision_provision import (  # type: ignore[import]
    provision_from_vision as semantic_provision_from_vision,
    _resolve_assistant_env,
    _resolve_model_from_settings,
    _resolve_vision_strict_output,
    _resolve_vision_use_kb,
)
from ui.services.vision_provision import (  # type: ignore[import]
    provision_from_vision as ui_provision_from_vision,
)
import yaml  # type: ignore[import]


LOGGER = logging.getLogger("tools.vision_debug_dummy")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
)


@dataclass
class DummyVisionCtx:
    """
    Context minimale per Vision, compatibile con semantic.vision_provision:

    - base_dir: root del workspace dummy (es. output/timmy-kb-dummy)
    - client_name: solo per log/contesto
    - settings: dict con sezione 'vision' (assistant_id_env, model, use_kb, strict_output, snapshot_retention_days)
    """

    base_dir: Path
    client_name: str
    settings: Dict[str, Any]


def _load_dummy_config(workspace: Path) -> Dict[str, Any]:
    cfg_path = workspace / "config" / "config.yaml"
    if not cfg_path.exists():
        raise ConfigError(f"config.yaml non trovato: {cfg_path}", slug="dummy", file_path=str(cfg_path))
    text = cfg_path.read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def _build_vision_settings_from_dummy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Estrarre solo i pezzi che interessano a semantic.vision_provision,
    convertendo da schema 'ai.vision.*' a schema minimal 'vision.*'.
    """
    ai_section = cfg.get("ai", {}) or {}
    vision_cfg = ai_section.get("vision", {}) or {}

    return {
        "vision": {
            "assistant_id_env": vision_cfg.get("assistant_id_env", "OBNEXT_ASSISTANT_ID"),
            "model": vision_cfg.get("model"),
            "snapshot_retention_days": vision_cfg.get("snapshot_retention_days", 30),
            "strict_output": bool(vision_cfg.get("strict_output", False)),
            "use_kb": bool(vision_cfg.get("use_kb", True)),
        },
        # Altre sezioni sono opzionali ma manteniamo struttura simile ai test
        "openai": cfg.get("ai", {}).get("openai", {}),
        "ui": cfg.get("ui", {}),
        "retriever": cfg.get("pipeline", {}).get("retriever", {"throttle": {}}),
        "ops": cfg.get("ops", {}),
        "finance": cfg.get("finance", {}),
    }


def _make_dummy_ctx(workspace: Path) -> DummyVisionCtx:
    cfg = _load_dummy_config(workspace)
    vision_settings = _build_vision_settings_from_dummy(cfg)
    client_name = cfg.get("client_name") or cfg.get("meta", {}).get("client_name") or "Dummy Srl"
    return DummyVisionCtx(
        base_dir=workspace,
        client_name=str(client_name),
        settings=vision_settings,
    )


def _print_ctx_summary(ctx: DummyVisionCtx, slug: str, pdf_path: Path) -> None:
    # Wrappiamo ctx in qualcosa con gli stessi attributi usati da helper semantic
    ctx_ns = SimpleNamespace(base_dir=ctx.base_dir, client_name=ctx.client_name, settings=ctx.settings)

    assistant_env = _resolve_assistant_env(ctx_ns)
    model_from_settings = _resolve_model_from_settings(ctx_ns)
    strict_output = _resolve_vision_strict_output(ctx_ns)
    use_kb = _resolve_vision_use_kb(ctx_ns)

    LOGGER.info("=== Vision debug: contesto risolto ===")
    LOGGER.info("slug: %s", slug)
    LOGGER.info("base_dir: %s", ctx.base_dir)
    LOGGER.info("pdf_path: %s", pdf_path)
    LOGGER.info("client_name: %s", ctx.client_name)
    LOGGER.info("assistant_id_env: %s", assistant_env)
    LOGGER.info("vision.model (da settings): %r", model_from_settings)
    LOGGER.info("vision.strict_output: %r", strict_output)
    LOGGER.info("vision.use_kb: %r", use_kb)


def _run_semantic_direct(ctx: DummyVisionCtx, slug: str, pdf_path: Path, model_override: Optional[str]) -> None:
    """
    Chiama direttamente semantic.provision_from_vision, che a sua volta:
    - costruisce il prompt
    - risolve assistant_id e model
    - chiama client.responses.create(...)
    """
    ctx_ns = SimpleNamespace(base_dir=ctx.base_dir, client_name=ctx.client_name, settings=ctx.settings)

    LOGGER.info("=== Esecuzione semantic.provision_from_vision (direct) ===")
    try:
        result = semantic_provision_from_vision(
            ctx=ctx_ns,
            logger=LOGGER,
            slug=slug,
            pdf_path=pdf_path,
            model=(model_override or ""),
        )
        LOGGER.info("Vision OK (semantic). Output:")
        LOGGER.info(json.dumps(result, indent=2, ensure_ascii=False))
    except ConfigError as exc:
        LOGGER.error("ConfigError da semantic.provision_from_vision: %s", exc)
        LOGGER.error("Dettagli: slug=%s, file_path=%s", getattr(exc, "slug", None), getattr(exc, "file_path", None))
        LOGGER.debug("Traceback completo:\n%s", traceback.format_exc())
    except Exception as exc:  # pragma: no cover - debug tool
        LOGGER.error("Eccezione generica da semantic.provision_from_vision: %s", exc)
        LOGGER.debug("Traceback completo:\n%s", traceback.format_exc())


def _run_ui_bridge(ctx: DummyVisionCtx, slug: str, pdf_path: Path, model_override: Optional[str]) -> None:
    """
    Chiama la versione UI `ui.services.vision_provision.provision_from_vision`,
    che include il gate hash/sentinel e poi delega al layer semantic.
    """
    ctx_ns = SimpleNamespace(base_dir=ctx.base_dir, client_name=ctx.client_name, settings=ctx.settings)

    LOGGER.info("=== Esecuzione ui.services.vision_provision.provision_from_vision (bridge UI) ===")
    try:
        result = ui_provision_from_vision(
            ctx=ctx_ns,
            logger=LOGGER,
            slug=slug,
            pdf_path=pdf_path,
            force=True,  # forziamo rigenerazione per evitare gate hash
            model=model_override,
            prepared_prompt=None,
        )
        LOGGER.info("Vision OK (UI bridge). Output:")
        LOGGER.info(json.dumps(result, indent=2, ensure_ascii=False))
    except ConfigError as exc:
        LOGGER.error("ConfigError da UI provision_from_vision: %s", exc)
        LOGGER.error("Dettagli: slug=%s, file_path=%s", getattr(exc, "slug", None), getattr(exc, "file_path", None))
        LOGGER.debug("Traceback completo:\n%s", traceback.format_exc())
    except Exception as exc:  # pragma: no cover - debug tool
        LOGGER.error("Eccezione generica da UI provision_from_vision: %s", exc)
        LOGGER.debug("Traceback completo:\n%s", traceback.format_exc())


def main(argv: Optional[list[str]] = None) -> None:
    ensure_dotenv_loaded()

    args = argv if argv is not None else sys.argv[1:]
    slug = args[0] if args else "dummy"

    workspace = REPO_ROOT / "output" / f"timmy-kb-{slug}"
    if not workspace.exists():
        print(f"[ERRORE] Workspace non trovato: {workspace}")
        raise SystemExit(1)

    pdf_path = workspace / "config" / "VisionStatement.pdf"
    if not pdf_path.exists():
        print(f"[ERRORE] VisionStatement.pdf non trovato: {pdf_path}")
        raise SystemExit(1)

    try:
        ctx = _make_dummy_ctx(workspace)
    except ConfigError as exc:
        print(f"[ERRORE CONFIG] {exc}")
        raise SystemExit(1)

    _print_ctx_summary(ctx, slug=slug, pdf_path=pdf_path)

    # Usa il modello configurato in ai.vision.model come override esplicito
    model_cfg = ctx.settings.get("vision", {}).get("model")
    LOGGER.info("Model override usato per il run: %r", model_cfg)

    # 1) Chiamata diretta al layer semantic (senza gate UI)
    _run_semantic_direct(ctx, slug=slug, pdf_path=pdf_path, model_override=model_cfg)

    # 2) Chiamata via bridge UI (replica più fedele del comportamento reale)
    _run_ui_bridge(ctx, slug=slug, pdf_path=pdf_path, model_override=model_cfg)


if __name__ == "__main__":
    main()
