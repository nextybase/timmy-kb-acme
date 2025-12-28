# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import inspect
from importlib import import_module


def _sig(fn: object) -> list[tuple[inspect._ParameterKind, str, object]]:
    signature = inspect.signature(fn)
    return [(param.kind, param.name, param.default) for param in signature.parameters.values()]


def test_semantics_ui_facade_signatures_match() -> None:
    api = import_module("semantic.api")
    expected = {
        "convert_markdown": [
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "context", inspect._empty),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "logger", inspect._empty),
            (inspect.Parameter.KEYWORD_ONLY, "slug", inspect._empty),
        ],
        "enrich_frontmatter": [
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "context", inspect._empty),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "logger", inspect._empty),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "vocab", inspect._empty),
            (inspect.Parameter.KEYWORD_ONLY, "slug", inspect._empty),
            (inspect.Parameter.KEYWORD_ONLY, "allow_empty_vocab", False),
        ],
        "write_summary_and_readme": [
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "context", inspect._empty),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "logger", inspect._empty),
            (inspect.Parameter.KEYWORD_ONLY, "slug", inspect._empty),
        ],
    }
    for name, expected_sig in expected.items():
        fn = getattr(api, name)
        assert _sig(fn) == expected_sig
