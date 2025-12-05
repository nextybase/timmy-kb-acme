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

# --- ensure repo root & src are on sys.path ---------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
# metti prima src (cosÃ¬ importiamo "ui.*"), poi root (per fallback "src.ui.*")
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(REPO_ROOT))

from pipeline.env_utils import ensure_dotenv_loaded, get_bool, get_env_var
from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import ensure_within_and_resolve

# ---- UI config (SSoT del modello Vision) -------------------------------------
try:
    from ui.config_store import get_vision_model  # type: ignore
except Exception:
    try:
        from src.ui.config_store import get_vision_model  # type: ignore
    except Exception:

        def get_vision_model(default: str = "gpt-4o-mini-2024-07-18") -> str:  # type: ignore
            return default


def _optional_env(name: str) -> Optional[str]:
    try:
        return get_env_var(name)
    except KeyError:
        return None
    except Exception:
        return None


def _is_gate_error(exc: BaseException) -> bool:
    """Riconosce l'eccezione del gate Vision giÃ  eseguito."""
    normalized = unicodedata.normalize("NFKD", str(exc)).casefold()
    return "vision" in normalized and "gia" in normalized and "eseguito" in normalized


def _existing_vision_artifacts(base_dir: Path) -> Dict[str, str]:
    """Restituisce i path agli artefatti Vision giÃ  presenti (se esistono)."""
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


# ---- Vision UI API (primary: ui.*, fallback: src.ui.*) ----------------------
try:
    from ui.services.vision_provision import run_vision  # type: ignore
except Exception:
    try:
        from src.ui.services.vision_provision import run_vision  # type: ignore
    except Exception as e:
        _print_err({"error": f"Impossibile importare run_vision: {e}"}, 1)

# ---- semantic module for monkey-patch (primary: semantic.*, fallback: src.semantic.*)
try:
    vp = importlib.import_module("semantic.vision_provision")
except Exception:
    try:
        vp = importlib.import_module("src.semantic.vision_provision")
    except Exception as e:
        _print_err({"error": f"Impossibile importare semantic.vision_provision: {e}"}, 1)


# ---- tracing wrappers (catturano thread_id/run_id e permettono steps/messages)
class _RunsWrapper:
    def __init__(self, beta_wrapper: "_BetaWrapper", runs: Any):
        self._beta = beta_wrapper
        self._runs = runs

    def create_and_poll(self, *args, **kwargs):
        thread_id = kwargs.get("thread_id") or (args[0] if args else None)
        resp = self._runs.create_and_poll(*args, **kwargs)
        self._beta._last_thread_id = thread_id
        self._beta._last_run_id = getattr(resp, "id", None)
        return resp

    def __getattr__(self, name):
        return getattr(self._runs, name)


class _ThreadsWrapper:
    def __init__(self, beta_wrapper: "_BetaWrapper", threads: Any):
        self._beta = beta_wrapper
        self._threads = threads
        self.runs = _RunsWrapper(beta_wrapper, threads.runs)
        self.messages = threads.messages

    def create(self, *args, **kwargs):
        t = self._threads.create(*args, **kwargs)
        self._beta._last_thread_id = getattr(t, "id", None)
        return t

    def __getattr__(self, name):
        return getattr(self._threads, name)


class _BetaWrapper:
    def __init__(self, client: "TracingClient", beta: Any):
        self._client = client
        self._beta = beta
        self._last_thread_id: Optional[str] = None
        self._last_run_id: Optional[str] = None
        self.threads = _ThreadsWrapper(self, beta.threads)

    def __getattr__(self, name):
        return getattr(self._beta, name)


class TracingClient:
    def __init__(self, original: Any):
        self._orig = original
        self.beta = _BetaWrapper(self, original.beta)

    def __getattr__(self, name):
        return getattr(self._orig, name)


# ---- guardie ambiente / .env -----------------------------------------------
def _require_env() -> None:
    """Richiede OPENAI_API_KEY + OBNEXT_ASSISTANT_ID/ASSISTANT_ID, altrimenti esce (2)."""
    try:
        api_key = get_env_var("OPENAI_API_KEY", required=True)
    except KeyError:
        api_key = None
    assistant_id = _optional_env("OBNEXT_ASSISTANT_ID") or _optional_env("ASSISTANT_ID")
    if not api_key or not assistant_id:
        _print_err(
            {
                "error": "OPENAI_API_KEY e OBNEXT_ASSISTANT_ID/ASSISTANT_ID sono obbligatori.",
                "missing": {
                    "OPENAI_API_KEY": bool(api_key),
                    "ASSISTANT_ID": bool(assistant_id),
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
                "error": "VISION_USE_KB Ã¨ disabilitata ma l'healthcheck richiede la KB attiva.",
                "hint": "Rimuovi VISION_USE_KB oppure impostala a 1",
            },
            3,
        )


def _extract_text_and_annotations(client: TracingClient, thread_id: str):
    """Estrae primo testo assistant + annotations (file_id/quote) dalle ultime 10 messages."""
    msgs = client._orig.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=10)
    text = ""
    annotations: List[Dict[str, Any]] = []
    for msg in getattr(msgs, "data", []) or []:
        if getattr(msg, "role", "") != "assistant":
            continue
        for part in getattr(msg, "content", None) or []:
            t = getattr(part, "type", None)
            if t in ("output_text", "text"):
                txt = getattr(getattr(part, "text", None), "value", None)
                if isinstance(txt, str) and txt.strip() and not text:
                    text = txt.strip()
                for ann in getattr(getattr(part, "text", None), "annotations", []) or []:
                    file_id = getattr(ann, "file_id", None) or getattr(ann, "file", None)
                    quote = getattr(ann, "quote", None)
                    rec = {"type": getattr(ann, "type", None)}
                    if file_id:
                        rec.update({"file_id": file_id, "quote": quote})
                        annotations.append(rec)
        if text:
            break
    return text, annotations


def _resolve_filenames(client: TracingClient, file_ids: List[str]) -> Dict[str, Optional[str]]:
    """file_id -> filename (best-effort)."""
    out: Dict[str, Optional[str]] = {}
    for fid in file_ids:
        try:
            f = client.files.retrieve(fid)
            out[fid] = getattr(f, "filename", None) or getattr(f, "name", None)
        except Exception:
            out[fid] = None
    return out


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

    orig_factory = getattr(vp, "make_openai_client", None)
    if orig_factory is None:
        raise HealthcheckError({"error": "make_openai_client non trovato in semantic.vision_provision"}, 1)

    LAST_CLIENT: Dict[str, Any] = {}

    def _tracing_factory():
        real = orig_factory()
        traced = TracingClient(real)
        LAST_CLIENT["client"] = traced
        return traced

    setattr(vp, "make_openai_client", _tracing_factory)

    class _Ctx:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir
            self.client_name = slug
            self.settings = {}

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
    traced_client: Optional[TracingClient] = None
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
        traced_client = LAST_CLIENT.get("client")  # type: ignore[assignment]
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

    if not run_skipped:
        traced: TracingClient = traced_client  # type: ignore[assignment]
        if traced is None or traced.beta._last_thread_id is None or traced.beta._last_run_id is None:
            raise HealthcheckError(
                {"error": "Tracing non riuscito: nessun thread/run ID catturato."},
                1,
            )

        thread_id = traced.beta._last_thread_id
        run_id = traced.beta._last_run_id

        try:
            steps = traced._orig.beta.threads.runs.steps.list(
                thread_id=thread_id,
                run_id=run_id,
            )
            for st in getattr(steps, "data", []) or []:
                tool = getattr(st, "type", None) or getattr(st, "step_type", None)
                if "tool" in str(tool).lower():
                    name = getattr(getattr(st, "tool", None), "name", None)
                    if name == "file_search":
                        used_file_search = True
                        break
        except Exception:
            used_file_search = False

        text, annotations = _extract_text_and_annotations(traced, thread_id)
        file_ids = [a.get("file_id") for a in annotations if a.get("file_id")]
        id_to_name = _resolve_filenames(traced, list(dict.fromkeys(file_ids))) if file_ids else {}

        for a in annotations:
            fid = a.get("file_id")
            if not fid:
                continue
            citations.append({"file_id": fid, "filename": id_to_name.get(fid), "quote": a.get("quote")})

        excerpt = (text or "").strip()
        if len(excerpt) > 400:
            excerpt = excerpt[:400].rstrip() + "..."

    mapping_text: Optional[str] = None
    try:
        mp = vision_result.get("mapping")
        if mp:
            mapping_text = Path(mp).read_text(encoding="utf-8")
    except Exception:
        mapping_text = None

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

    parser = argparse.ArgumentParser(
        description="Healthcheck E2E Vision (usa Vision reale + tracing Assistente)"
    )
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
