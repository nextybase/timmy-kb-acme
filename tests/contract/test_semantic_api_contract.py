# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import inspect

import semantic.api


def test_run_semantic_pipeline_signature_stable() -> None:
    sig = inspect.signature(semantic.api.run_semantic_pipeline)
    assert "slug" in sig.parameters
    assert sig.parameters["slug"].kind is inspect.Parameter.KEYWORD_ONLY
