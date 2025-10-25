# scripts/kb_healthcheck.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- ensure repo root & src are on sys.path ---------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
# metti prima src (così importiamo "ui.*"), poi root (per fallback "src.ui.*")
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(REPO_ROOT))

from pipeline.env_utils import ensure_dotenv_loaded, get_bool, get_env_var
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
                "error": "VISION_USE_KB è disabilitata ma l'healthcheck richiede la KB attiva.",
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
    parser.add_argument("--model", default=None, help="Annotazione modello (per sentinel hash)")
    args = parser.parse_args()

    slug = args.slug.strip()
    base_dir = _client_base(slug)
    pdf_path = _repo_pdf_path()
    if not pdf_path.exists():
        _print_err(
            {"error": "VisionStatement non trovato", "expected": str(pdf_path)},
            1,
        )

    # Monkey-patch: sostituiamo la factory OpenAI usata da Vision per inserire il client tracciante
    orig_factory = getattr(vp, "make_openai_client", None)
    if orig_factory is None:
        _print_err({"error": "make_openai_client non trovato in semantic.vision_provision"}, 1)

    LAST_CLIENT: Dict[str, Any] = {}

    def _tracing_factory():
        real = orig_factory()
        traced = TracingClient(real)
        LAST_CLIENT["client"] = traced
        return traced

    setattr(vp, "make_openai_client", _tracing_factory)

    # Esecuzione Vision reale (UI -> semantic -> Assistants)
    class _Ctx:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir
            self.client_name = slug
            self.settings = {}

    ctx = _Ctx(base_dir)
    logger = logging.getLogger("healthcheck.vision")
    logger.setLevel(logging.INFO)

    try:
        vision_result = run_vision(
            ctx=ctx, slug=slug, pdf_path=pdf_path, force=args.force, model=args.model, logger=logger
        )
    except Exception as e:
        _print_err({"error": f"Vision failed: {e}"}, 1)

    traced: TracingClient = LAST_CLIENT.get("client")  # type: ignore
    if traced is None or traced.beta._last_thread_id is None or traced.beta._last_run_id is None:
        _print_err({"error": "Tracing non riuscito: nessun thread/run ID catturato."}, 1)

    # Verifica steps: uso effettivo di file_search
    try:
        steps = traced._orig.beta.threads.runs.steps.list(
            thread_id=traced.beta._last_thread_id, run_id=traced.beta._last_run_id
        )
        used_file_search = False
        for st in getattr(steps, "data", []) or []:
            tool = getattr(st, "type", None) or getattr(st, "step_type", None)
            if "tool" in str(tool).lower():
                name = getattr(getattr(st, "tool", None), "name", None)
                if name == "file_search":
                    used_file_search = True
                    break
    except Exception:
        used_file_search = False

    # Estrai testo e citazioni
    text, annotations = _extract_text_and_annotations(traced, traced.beta._last_thread_id)
    file_ids = [a.get("file_id") for a in annotations if a.get("file_id")]
    id_to_name = _resolve_filenames(traced, list(dict.fromkeys(file_ids))) if file_ids else {}

    citations = []
    for a in annotations:
        fid = a.get("file_id")
        if not fid:
            continue
        citations.append({"file_id": fid, "filename": id_to_name.get(fid), "quote": a.get("quote")})

    excerpt = (text or "").strip()
    if len(excerpt) > 400:
        excerpt = excerpt[:400].rstrip() + "…"

    # carica (se presente) il contenuto del semantic_mapping.yaml
    mapping_text: Optional[str] = None
    try:
        mp = vision_result.get("mapping")
        if mp:
            mapping_text = Path(mp).read_text(encoding="utf-8")
    except Exception:
        mapping_text = None

    out = {
        "status": "completed",
        "used_file_search": bool(used_file_search or bool(file_ids)),
        "citations": citations,
        "assistant_text_excerpt": excerpt,
        "thread_id": traced.beta._last_thread_id,
        "run_id": traced.beta._last_run_id,
        "pdf_path": str(pdf_path),
        "base_dir": str(base_dir),
        "mapping_yaml": vision_result.get("mapping"),
        "cartelle_raw_yaml": vision_result.get("cartelle_raw"),
        "semantic_mapping_content": mapping_text,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not out["used_file_search"] and not citations:
        # Caso "soft-fail" specifico dell'healthcheck KB (assistente non ha usato file_search / niente citazioni)
        sys.exit(3)


if __name__ == "__main__":
    main()
