# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""Shim compatibile che re-esporta l'orchestratore `tag_onboarding` in `timmy_kb.cli`."""

from pipeline.cli_runner import run_cli_orchestrator
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from timmy_kb.cli.tag_onboarding import _parse_args, _resolve_cli_paths, _should_proceed
from timmy_kb.cli.tag_onboarding import main as _timmy_main
from timmy_kb.cli.tag_onboarding import run_nlp_to_db, tag_onboarding_main, validate_tags_reviewed
from timmy_kb.cli.tag_onboarding_context import ContextResources, prepare_context

__all__ = [
    "_parse_args",
    "_resolve_cli_paths",
    "_should_proceed",
    "run_nlp_to_db",
    "tag_onboarding_main",
    "validate_tags_reviewed",
    "main",
    "ContextResources",
    "prepare_context",
    "ConfigError",
    "ClientContext",
]

main = _timmy_main


if __name__ == "__main__":
    run_cli_orchestrator("tag_onboarding", _parse_args, _timmy_main)
