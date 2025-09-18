"""Prompt builder for Timmy KB Coder.

build_prompt(next_premise, coding_rules, task, retrieved) -> str

If `retrieved` is not empty, append a "Retrieved Context" section with enumerated
blocks [1]..[n]. Also include brief micro-citations instruction.

Output requirements emphasize: web accessibility, performance, security, brief
design comments, modular and production-ready code.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger("timmy_kb.prompt_builder")


def _format_retrieved(retrieved: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, item in enumerate(retrieved, start=1):
        content = item.get("content", "").strip()
        score = item.get("score")
        meta = item.get("meta", {})
        header = (
            f"[#{i}] score={score:.3f} meta={meta}"
            if isinstance(score, (int, float))
            else f"[#{i}] meta={meta}"
        )
        parts.append(f"{header}\n\n{content}")
    return "\n\n".join(parts)


def build_prompt(
    next_premise: str, coding_rules: str, task: str, retrieved: list[dict[str, Any]]
) -> str:
    """Compose the final prompt for the coding agent."""
    lines: list[str] = []
    lines.append("# Timmy KB Coder — Request")

    if next_premise.strip():
        lines.append("\n## NeXT Premise")
        lines.append(next_premise.strip())

    lines.append("\n## Task")
    lines.append(task.strip() or "<no task provided>")

    if retrieved:
        lines.append("\n## Retrieved Context")
        lines.append(_format_retrieved(retrieved))
        lines.append(
            "\nUse the Retrieved Context micro-citations like [#1], [#2] inline where relevant."
        )

    lines.append("\n## Coding Rules (Web)")
    if coding_rules.strip():
        lines.append(coding_rules.strip())
    lines.append(
        "\n- Accessibility: ARIA, keyboard nav, color contrast."
        "\n- Performance: async loading, minimal bundles, caching, avoid layout thrash."
        "\n- Security: sanitize inputs, escape output, CSP hints, avoid eval, HTTPS."
        "\n- Code: brief design comments, modular, testable, production-ready."
    )

    prompt = "\n".join(lines).strip() + "\n"
    LOGGER.info("Prompt built, length=%d chars", len(prompt))
    return prompt
