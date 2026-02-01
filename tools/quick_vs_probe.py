# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import time

from openai import APIConnectionError, APIStatusError, OpenAI

c = OpenAI()
try:
    vs = c.vector_stores.create(name=f"diag-{int(time.time())}")
    vs_id = getattr(vs, "id", None) or (vs.get("id") if isinstance(vs, dict) else None)
    print("Vector Store created:", vs_id)
    sys.exit(0)
except APIConnectionError as e:
    print("APIConnectionError (network):", e)
    sys.exit(2)
except APIStatusError as e:
    print("APIStatusError (server/status):", getattr(e, "status_code", "?"), getattr(e, "response", None))
    sys.exit(3)
except Exception as e:
    print("Generic exception:", type(e).__name__, e)
    sys.exit(1)
