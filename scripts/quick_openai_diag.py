# scripts/quick_openai_diag.py  — compatibile con openai >= 2.x (no temperature)
import os, sys, time, json
from openai import OpenAI, OpenAIError

def echo_env(name: str, *, show_value: bool = False) -> str:
    val = (os.getenv(name) or "").strip()
    if not val:
        return "<vuoto>"
    return val if show_value else "<impostato>"

def main() -> int:
    print("=== OpenAI Diagnostics (v2) ===")
    try:
        import openai
        print("openai version:", getattr(openai, "__version__", "(n/d)"))
    except Exception:
        print("openai version: (non disponibile)")

    print("OPENAI_API_KEY:", echo_env("OPENAI_API_KEY"))
    print("OPENAI_PROJECT:", echo_env("OPENAI_PROJECT"))
    print("OPENAI_BASE_URL:", echo_env("OPENAI_BASE_URL", show_value=True) or "https://api.openai.com/v1")

    asst = (os.getenv("OBNEXT_ASSISTANT_ID") or os.getenv("ASSISTANT_ID") or "").strip()
    print("ASSISTANT_ID/OBNEXT_ASSISTANT_ID:", "<vuoto>" if not asst else "<impostato>")

    try:
        c = OpenAI()
    except OpenAIError as e:
        print("ERRORE: client non inizializzato:", e); return 2

    has_responses = bool(getattr(c, "responses", None) or getattr(getattr(c, "beta", None), "responses", None))
    vs_ns = getattr(c, "vector_stores", None) or getattr(getattr(c, "beta", None), "vector_stores", None)
    has_vs = bool(vs_ns)
    print("has responses API:", has_responses)
    print("has vector_stores API:", has_vs)

    # 1) Responses "model-only" con Structured Outputs (v2: text.format con name+schema+strict)
    if has_responses:
        try:
            schema_core = {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            }
            fmt = {
                "type": "json_schema",
                "name": "ping",
                "schema": schema_core,
                "strict": True,
            }
            r = c.responses.create(
                model=os.getenv("VISION_MODEL", "o4-mini"),
                input='Restituisci SOLO {"ok": true}',
                text={"format": fmt},
                # niente temperature in v2 su alcuni modelli con structured outputs
            )
            parsed = getattr(r, "output_parsed", None)
            if parsed is None:
                try:
                    parsed = json.loads(getattr(r, "output_text", ""))
                except Exception:
                    parsed = None
            print("responses (model-only):", "OK" if isinstance(parsed, dict) and parsed.get("ok") is True else parsed)
        except Exception as e:
            print("responses (model-only): ERRORE →", e); return 4
    else:
        print("responses: NON disponibile (SDK troppo vecchio?)"); return 4

    # 2) (Opzionale) Responses con assistant_id
    if asst and has_responses:
        try:
            fmt2 = {
                "type": "json_schema",
                "name": "ping2",
                "schema": {"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"],"additionalProperties":False},
                "strict": True,
            }
            r = c.responses.create(
                assistant_id=asst,
                input=[{"role": "user", "content": 'Restituisci SOLO {"ok": true}'}],
                text={"format": fmt2},
            )
            parsed = getattr(r, "output_parsed", None)
            if parsed is None:
                try:
                    parsed = json.loads(getattr(r, "output_text", ""))
                except Exception:
                    parsed = None
            print("responses (assistant_id):", "OK" if isinstance(parsed, dict) and parsed.get("ok") is True else parsed)
        except Exception as e:
            print("responses (assistant_id): ERRORE (non bloccante) →", e)
    else:
        print("responses (assistant_id): saltato (ID non impostato)")

    # 3) Vector Store create/delete (smoke, non bloccante)
    if has_vs:
        try:
            vs = vs_ns.create(name=f"smoke-{int(time.time())}")  # type: ignore[attr-defined]
            vid = getattr(vs, "id", None) or (isinstance(vs, dict) and vs.get("id"))
            print("vector_stores.create:", "OK (id: %s)" % (vid or "n/d"))
            try:
                if hasattr(vs_ns, "delete"):
                    vs_ns.delete(vid)  # type: ignore[attr-defined]
                    print("vector_stores.delete: OK")
            except Exception:
                pass
        except Exception as e:
            print("vector_stores.create: ERRORE (non bloccante) →", e)
    else:
        print("vector_stores: namespace non disponibile (OK se lavori in inline)")

    print("=== Diagnostica completata ==="); return 0

if __name__ == "__main__":
    sys.exit(main())
