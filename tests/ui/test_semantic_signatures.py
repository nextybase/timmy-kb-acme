# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import inspect
from importlib import import_module


def _sig(fn: object) -> list[tuple[inspect._ParameterKind, str, object]]:
    signature = inspect.signature(fn)
    return [(param.kind, param.name, param.default) for param in signature.parameters.values()]


def test_semantics_ui_facade_signatures_match() -> None:
    expected = {
        "semantic.convert_service:convert_markdown": [
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "context", inspect._empty),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "logger", inspect._empty),
            (inspect.Parameter.KEYWORD_ONLY, "slug", inspect._empty),
        ],
        "semantic.frontmatter_service:enrich_frontmatter": [
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "context", inspect._empty),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "logger", inspect._empty),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "vocab", inspect._empty),
            (inspect.Parameter.KEYWORD_ONLY, "slug", inspect._empty),
            (inspect.Parameter.KEYWORD_ONLY, "allow_empty_vocab", False),
        ],
        "semantic.frontmatter_service:write_summary_and_readme": [
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "context", inspect._empty),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, "logger", inspect._empty),
            (inspect.Parameter.KEYWORD_ONLY, "slug", inspect._empty),
        ],
    }
    for locator, expected_sig in expected.items():
        module_name, func_name = locator.split(":", 1)
        module = import_module(module_name)
        fn = getattr(module, func_name)
        assert _sig(fn) == expected_sig
