# SPDX-License-Identifier: GPL-3.0-or-later
# tools/kb_healthcheck.py
# -*- coding: utf-8 -*-
"""
DUMMY / SMOKE SUPER-TEST ONLY
FORBIDDEN IN RUNTIME-CORE (src/)
Fallback behavior is intentional and confined to this perimeter
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

from pipeline.env_utils import ensure_dotenv_loaded, get_bool, get_env_var
from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.config_store import get_vision_model  # type: ignore
from ui.services.vision_provision import run_vision  # type: ignore
import yaml


def _optional_env(name: str) -> Optional[str]:
    try:
        return get_env_var(name)
    except KeyError:
        return None
    except Exception:
        return None


def _existing_vision_artifacts(base_dir: Path) -> Dict[str, str]:
    """Restituisce i path agli artefatti Vision già presenti (se esistono)."""
    payload = {"mapping": ""}
    try:
        semantic_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "semantic"))
    except Exception:
        return payload

    mapping = semantic_dir / "semantic_mapping.yaml"
    if mapping.exists():
        payload["mapping"] = str(mapping)
    return payload


def _verify_offline_artifacts(base_dir: Path, repo_pdf: Path) -> Dict[str, Any]:
    semantic_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "semantic"))
    mapping = semantic_dir / "semantic_mapping.yaml"
    workspace_pdf = Path(ensure_within_and_resolve(base_dir, base_dir / "config" / "VisionStatement.pdf"))

    missing: List[str] = []
    if not mapping.exists():
        missing.append(str(mapping))
    if not workspace_pdf.exists():
        missing.append(str(workspace_pdf))

    if missing:
        return {"ok": False, "missing": missing, "paths": {}}

    try:
        if workspace_pdf.read_bytes() != repo_pdf.read_bytes():
            return {
                "ok": False,
                "missing": [],
                "paths": {
                    "mapping": str(mapping),
                    "vision_pdf": str(workspace_pdf),
                },
                "error": "VisionStatement.pdf non sincronizzato con la repo.",
            }
    except Exception as exc:
        return {
            "ok": False,
            "missing": [],
            "paths": {
                "mapping": str(mapping),
                "vision_pdf": str(workspace_pdf),
            },
            "error": f"Impossibile leggere VisionStatement.pdf: {exc}",
        }

    return {
        "ok": True,
        "missing": [],
        "paths": {
            "mapping": str(mapping),
            "vision_pdf": str(workspace_pdf),
        },
    }


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


def _should_log_runtime_diagnostics() -> bool:
    return bool(get_bool("DEBUG_RUNTIME", default=False) or get_bool("DEBUG", default=False))


def _log_runtime_diagnostics(logger: logging.Logger) -> None:
    """DEBUG_RUNTIME: diagnostica opt-in; UI/Streamlit deve usare lo stesso interpreter/venv della CLI."""
    if not _should_log_runtime_diagnostics():
        return
    if getattr(_log_runtime_diagnostics, "_done", False):
        return
    _log_runtime_diagnostics._done = True  # type: ignore[attr-defined]

    try:
        import openai  # type: ignore

        openai_version = getattr(openai, "__version__", "unknown")
        openai_file = getattr(openai, "__file__", "unknown")
    except Exception as exc:
        openai_version = f"unavailable:{type(exc).__name__}"
        openai_file = "unavailable"

    logger.info(
        "healthcheck.runtime.diagnostics | exe=%s openai=%s cwd=%s",
        sys.executable,
        openai_version,
        os.getcwd(),
        extra={
            "sys_executable": sys.executable,
            "sys_version": sys.version,
            "openai_version": openai_version,
            "openai_file": openai_file,
            "cwd": os.getcwd(),
            "sys_path_0": (sys.path[0] if sys.path else ""),
        },
    )


def _runtime_diagnostics_summary() -> str:
    try:
        import openai  # type: ignore

        openai_version = getattr(openai, "__version__", "unknown")
        openai_file = getattr(openai, "__file__", "unknown")
    except Exception as exc:
        openai_version = f"unavailable:{type(exc).__name__}"
        openai_file = "unavailable"
    return f"exe={sys.executable} openai={openai_version} file={openai_file}"


def _runtime_project_org_summary() -> str:
    project = os.environ.get("OPENAI_PROJECT") or ""
    org = os.environ.get("OPENAI_ORG") or ""
    parts: list[str] = []
    if project:
        parts.append(f"OPENAI_PROJECT={project}")
    if org:
        parts.append(f"OPENAI_ORG={org}")
    return " ".join(parts)


def _load_client_settings(base_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    cfg_path = ensure_within_and_resolve(base_dir, base_dir / "config" / "config.yaml")
    if not cfg_path.exists():
        return {}
    try:
        raw = read_text_safe(cfg_path.parent, cfg_path, encoding="utf-8")
        data = yaml.safe_load(raw) if raw else None
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(
            "healthcheck.config_load_failed",
            extra={"error": str(exc), "file_path": str(cfg_path)},
        )
        return {}


def run_healthcheck(
    slug: str,
    *,
    model: Optional[str] = None,
    include_prompt: bool = False,
    offline: bool = False,
) -> Dict[str, Any]:
    slug = slug.strip()
    base_dir = _client_base(slug)
    repo_pdf = _repo_pdf_path()
    if not repo_pdf.exists():
        raise HealthcheckError(
            {"error": "VisionStatement non trovato", "expected": str(repo_pdf)},
            1,
        )
    class _Ctx:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir
            self.client_name = slug
            self.settings: Dict[str, Any] = {}

    ctx = _Ctx(base_dir)
    logger = logging.getLogger("healthcheck.vision")
    logger.setLevel(logging.INFO)
    _log_runtime_diagnostics(logger)
    ctx.settings = _load_client_settings(base_dir, logger)

    if offline:
        verified = _verify_offline_artifacts(base_dir, repo_pdf)
        logger.info(
            "healthcheck.vision.offline_mode",
            extra={
                "slug": slug,
                "mapping": verified.get("paths", {}).get("mapping"),
                "vision_pdf": verified.get("paths", {}).get("vision_pdf"),
            },
        )
        if not verified.get("ok"):
            payload = {
                "error": "Vision offline validation failed",
                "missing": verified.get("missing", []),
                "paths": verified.get("paths", {}),
            }
            if verified.get("error"):
                payload["details"] = verified["error"]
            raise HealthcheckError(payload, 1)
        return {
            "status": "ok_offline",
            "base_dir": str(base_dir),
            "mapping_yaml": verified["paths"]["mapping"],
            "pdf_path": verified["paths"]["vision_pdf"],
        }

    workspace_pdf = _sync_workspace_pdf(base_dir, repo_pdf)
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

    try:
        vision_result = run_vision(
            ctx=ctx,
            slug=slug,
            pdf_path=workspace_pdf,
            model=effective_model,
            logger=logger,
            preview_prompt=False,
            prepared_prompt_override=prepared_prompt,
        )
    except Exception as exc:
        detail = str(exc)
        if _should_log_runtime_diagnostics():
            normalized = detail.casefold()
            if "response_format" in normalized and "unexpected keyword" in normalized:
                detail = f"{detail} | runtime: {_runtime_diagnostics_summary()}"
            elif (
                "insufficient_quota" in normalized
                or "exceeded your current quota" in normalized
                or "check your plan and billing" in normalized
                or "quota" in normalized
                or "429" in normalized
            ):
                env_suffix = _runtime_project_org_summary()
                suffix = _runtime_diagnostics_summary()
                if env_suffix:
                    suffix = f"{suffix} {env_suffix}"
                detail = f"{detail} | runtime: {suffix}"
        raise HealthcheckError({"error": f"Vision failed: {detail}"}, 1)

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
        "status": "completed",
        "used_file_search": bool(used_file_search),
        "citations": citations,
        "assistant_text_excerpt": excerpt,
        "thread_id": thread_id,
        "run_id": run_id,
        "pdf_path": str(workspace_pdf),
        "base_dir": str(base_dir),
        "mapping_yaml": vision_result.get("mapping"),
        "semantic_mapping_content": mapping_text,
        "vision_skipped": False,
    }
    if prompt_requested and prepared_prompt:
        out["prompt"] = prepared_prompt
    return out


# ---- main -------------------------------------------------------------------
def main() -> None:
    _load_env()

    parser = argparse.ArgumentParser(description="Healthcheck E2E Vision (usa Vision reale + tracing Assistente)")
    parser.add_argument("--slug", default="dummy", help="Slug cliente (default: dummy)")
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
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Valida artefatti Vision senza chiamate di rete",
    )
    args = parser.parse_args()

    if not args.offline:
        _require_env()
        _ensure_kb_enabled_or_fail()

    try:
        out = run_healthcheck(
            slug=args.slug,
            model=(args.model or get_vision_model()),
            include_prompt=bool(args.include_prompt),
            offline=bool(args.offline),
        )
    except HealthcheckError as exc:
        _print_err(exc.payload, exc.code)

    print(json.dumps(out, ensure_ascii=False, indent=2))

    if not out.get("used_file_search") and not out.get("citations"):
        sys.exit(3)


if __name__ == "__main__":
    main()
