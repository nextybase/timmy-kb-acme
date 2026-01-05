# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import inspect
import os
import sys


def main() -> int:
    print(f"prefix={sys.prefix} venv={os.environ.get('VIRTUAL_ENV', '')}")
    try:
        import openai  # type: ignore
    except Exception as exc:
        print(f"openai_import_error={type(exc).__name__}")
        return 1

    print(f"exe={sys.executable}")
    print(f"openai_version={getattr(openai, '__version__', 'unknown')}")
    print(f"openai_file={getattr(openai, '__file__', 'unknown')}")
    api_key = os.environ.get("OPENAI_API_KEY") or "dummy"
    try:
        client = openai.OpenAI(api_key=api_key)
        signature = inspect.signature(client.responses.create)
        print(f"responses_create_signature={signature}")
    except Exception as exc:
        print(f"responses_create_signature_error={type(exc).__name__}:{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
