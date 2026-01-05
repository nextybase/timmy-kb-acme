# SPDX-License-Identifier: GPL-3.0-only
# tools/kb_healthcheck.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

from pipeline.env_utils import ensure_dotenv_loaded, get_bool, get_env_var
from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import ensure_within_and_resolve
from ui.config_store import get_vision_model  # type: ignore
from ui.services.vision_provision import run_vision  # type: ignore


def _optional_env(name: str) -> Optional[str]:
    try:
        return get_env_var(name)
    except KeyError:
        return None
    except Exception:
        return None


def _is_gate_error(exc: BaseException) -> bool:
    """Riconosce l'eccezione del gate Vision già eseguito."""
    normalized = unicodedata.normalize("NFKD", str(exc)).casefold()
    return "vision" in normalized and "gia" in normalized and "eseguito" in normalized


def _existing_vision_artifacts(base_dir: Path) -> Dict[str, str]:
    """Restituisce i path agli artefatti Vision già presenti (se esistono)."""
    payload = {"mapping": "", "cartelle_raw": ""}
    try:
        semantic_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "semantic"))
    except Exception:
        return payload

    mapping = semantic_dir / "semantic_mapping.yaml"
    cartelle = semantic_dir / "cartelle_raw.yaml"
    if mapping.exists():
        payload["mapping"] = str(mapping)
    if cartelle.exists():
        payload["cartelle_raw"] = str(cartelle)
    return payload


class HealthcheckError(RuntimeError):
    def __init__(self, payload: Dict[str, Any], code: int) -> None:
        super().__init__(payload.get("error") or "healthcheck failed")
        self.payload = payload
        self.code = code


def _print_err(payload: Dict[str, Any], code: int) -> None:
    """Stampa JSON su stderr e termina con codice specifico."""
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def _client_base(slug: str) -> Path:
    """Radice workspace cliente (storico): <repo>/output/timmy-kb-<slug>."""
    return REPO_ROOT / "output" / f"timmy-kb-{slug}"


def _repo_pdf_path() -> Path:
    """Unico percorso ammesso: REPO_ROOT/config/VisionStatement.pdf (niente fallback)."""
    return REPO_ROOT / "config" / "VisionStatement.pdf"


def _sync_workspace_pdf(base_dir: Path, source_pdf: Path) -> Path:
    """
    Garantisce che il VisionStatement sia presente nel workspace (config/VisionStatement.pdf).

    Ritorna il percorso sicuro all'interno del workspace, copiando il PDF repo se assente
    o diverso (scrittura atomica).
    """
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    cfg_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "config"))
    cfg_dir.mkdir(parents=True, exist_ok=True)

    target = Path(ensure_within_and_resolve(cfg_dir, cfg_dir / "VisionStatement.pdf"))

    data = source_pdf.read_bytes()
    if target.exists():
        try:
            if target.read_bytes() == data:
                return target
        except Exception:
            # fall-back: riscrive in caso di errore di lettura
            pass

    safe_write_bytes(target, data, atomic=True)
    return target


# ---- semantic module for monkey-patch (only semantic.*) ----------------------
try:
    vp = importlib.import_module("semantic.vision_provision")
except Exception as e:
    _print_err({"error": f"Impossibile importare semantic.vision_provision: {e}"}, 1)


# ---- guardie ambiente / .env -----------------------------------------------
def _require_env() -> None:
    """Richiede OPENAI_API_KEY + OBNEXT_ASSISTANT_ID, altrimenti esce (2)."""
    try:
        api_key = get_env_var("OPENAI_API_KEY", required=True)
    except KeyError:
        api_key = None
    assistant_id = _optional_env("OBNEXT_ASSISTANT_ID")
    if not api_key or not assistant_id:
        _print_err(
            {
                "error": "OPENAI_API_KEY e OBNEXT_ASSISTANT_ID sono obbligatori.",
                "missing": {
                    "OPENAI_API_KEY": bool(api_key),
                    "OBNEXT_ASSISTANT_ID": bool(assistant_id),
                },
            },
            2,
        )


def _ensure_kb_enabled_or_fail() -> None:
    """Garantisce che la KB sia attiva per l'healthcheck Assistant."""
    current = _optional_env("VISION_USE_KB")
    if current is None:
        os.environ["VISION_USE_KB"] = "1"
        return
    if not get_bool("VISION_USE_KB", default=True):
        _print_err(
            {
                "error": "VISION_USE_KB è disabilitata ma l'healthcheck richiede la KB attiva.",
                "hint": "Rimuovi VISION_USE_KB oppure impostala a 1",
            },
            3,
        )


def _load_env() -> None:
    """Carica .env con l'helper centralizzato (best-effort)."""
    try:
        ensure_dotenv_loaded()
    except Exception:
        pass


def run_healthcheck(
    slug: str,
    *,
    force: bool = False,
    model: Optional[str] = None,
    include_prompt: bool = False,
) -> Dict[str, Any]:
    slug = slug.strip()
    base_dir = _client_base(slug)
    repo_pdf = _repo_pdf_path()
    if not repo_pdf.exists():
        raise HealthcheckError(
            {"error": "VisionStatement non trovato", "expected": str(repo_pdf)},
            1,
        )
    workspace_pdf = _sync_workspace_pdf(base_dir, repo_pdf)

    class _Ctx:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir
            self.client_name = slug
            self.settings: Dict[str, Any] = {}

    ctx = _Ctx(base_dir)
    logger = logging.getLogger("healthcheck.vision")
    logger.setLevel(logging.INFO)

    prepared_prompt: Optional[str] = None
    effective_model = model or get_vision_model()
    prompt_requested = bool(include_prompt)
    if prompt_requested:
        prepare_fn = getattr(vp, "prepare_assistant_input", None)
        if callable(prepare_fn):
            try:
                prepared_prompt = prepare_fn(
                    ctx=ctx,
                    slug=slug,
                    pdf_path=workspace_pdf,
                    model=effective_model,
                    logger=logger,
                )
            except Exception as exc:
                logger.warning("healthcheck.prompt_prepare_failed", extra={"error": str(exc)})
                prepared_prompt = None
        else:
            prompt_requested = False

    run_skipped = False
    try:
        vision_result = run_vision(
            ctx=ctx,
            slug=slug,
            pdf_path=workspace_pdf,
            force=force,
            model=effective_model,
            logger=logger,
            preview_prompt=False,
            prepared_prompt_override=prepared_prompt,
        )
    except Exception as exc:
        if prompt_requested and _is_gate_error(exc):
            run_skipped = True
            vision_result = _existing_vision_artifacts(base_dir)
        else:
            raise HealthcheckError({"error": f"Vision failed: {exc}"}, 1)

    used_file_search = False
    citations: List[Dict[str, Any]] = []
    excerpt = ""
    thread_id: Optional[str] = None
    run_id: Optional[str] = None

    mapping_text: Optional[str] = None
    try:
        mp = vision_result.get("mapping")
        if mp:
            mapping_text = Path(mp).read_text(encoding="utf-8")
    except Exception:
        mapping_text = None

    if mapping_text:
        excerpt = mapping_text.strip()
        if len(excerpt) > 400:
            excerpt = excerpt[:400].rstrip() + "..."
        used_file_search = True

    out: Dict[str, Any] = {
        "status": "skipped" if run_skipped else "completed",
        "used_file_search": bool(used_file_search),
        "citations": citations,
        "assistant_text_excerpt": excerpt,
        "thread_id": thread_id,
        "run_id": run_id,
        "pdf_path": str(workspace_pdf),
        "base_dir": str(base_dir),
        "mapping_yaml": vision_result.get("mapping"),
        "cartelle_raw_yaml": vision_result.get("cartelle_raw"),
        "semantic_mapping_content": mapping_text,
        "vision_skipped": run_skipped,
    }
    if prompt_requested and prepared_prompt:
        out["prompt"] = prepared_prompt
    return out


# ---- main -------------------------------------------------------------------
def main() -> None:
    _load_env()
    _require_env()
    _ensure_kb_enabled_or_fail()

    parser = argparse.ArgumentParser(description="Healthcheck E2E Vision (usa Vision reale + tracing Assistente)")
    parser.add_argument("--slug", default="dummy", help="Slug cliente (default: dummy)")
    parser.add_argument("--force", action="store_true", help="Forza rigenerazione Vision")
    parser.add_argument(
        "--model",
        default=None,
        help="Modello Vision; se omesso si usa il default configurato (get_vision_model())",
    )
    parser.add_argument(
        "--include-prompt",
        action="store_true",
        help="Include nel risultato JSON il prompt Vision generato",
    )
    args = parser.parse_args()

    try:
        out = run_healthcheck(
            slug=args.slug,
            force=bool(args.force),
            model=(args.model or get_vision_model()),
            include_prompt=bool(args.include_prompt),
        )
    except HealthcheckError as exc:
        _print_err(exc.payload, exc.code)

    print(json.dumps(out, ensure_ascii=False, indent=2))

    if out.get("vision_skipped"):
        sys.exit(0)
    if not out.get("used_file_search") and not out.get("citations"):
        sys.exit(3)


if __name__ == "__main__":
    main()
