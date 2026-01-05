# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import inspect
import os
import sys

import pytest


def test_openai_responses_signature_supports_response_format() -> None:
    try:
        import openai  # type: ignore
    except Exception as exc:
        pytest.fail(f"openai_import_error={type(exc).__name__}:{exc}")

    api_key = os.environ.get("OPENAI_API_KEY") or "dummy"
    client = openai.OpenAI(api_key=api_key)
    signature = inspect.signature(client.responses.create)
    supports = "text" in signature.parameters
    if not supports:
        exe = sys.executable
        version = getattr(openai, "__version__", "unknown")
        file_path = getattr(openai, "__file__", "unknown")
        pytest.fail(
            "openai.responses.create missing text; "
            f"exe={exe} openai={version} file={file_path} signature={signature}"
        )
