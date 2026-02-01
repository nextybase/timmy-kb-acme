# SPDX-License-Identifier: GPL-3.0-or-later
import ast
import json
import re
from pathlib import Path

import pytest

# Accetta solo eventi a snake/dot form, es. cli.onboarding.start
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._][a-z0-9]+)+$")
LEVELS = {"info", "warning", "error", "exception", "debug"}
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
BASELINE_PATH = Path(__file__).parent / "fixtures" / "logging_events_baseline.json"


def _is_logger_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in LEVELS:
        return False
    base = node.func.value
    name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
    return bool(name and "log" in name)


def _extract_message_arg(node: ast.Call) -> str | None:
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _extract_extra_event(node: ast.Call) -> str | None:
    for kw in node.keywords:
        if kw.arg != "extra" or not isinstance(kw.value, ast.Dict):
            continue
        for key_node, value_node in zip(kw.value.keys, kw.value.values, strict=False):
            if isinstance(key_node, ast.Constant) and key_node.value == "event":
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    return value_node.value
    return None


def _collect_issues() -> dict[str, set[tuple]]:
    issues: dict[str, set[tuple]] = {
        "freeform": set(),
        "missing_extra": set(),
        "event_mismatch": set(),
        "invalid_event": set(),
    }

    for path in SRC_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_logger_call(node)):
                continue
            rel_path = path.relative_to(REPO_ROOT).as_posix()
            message = _extract_message_arg(node)
            has_extra = any(kw.arg == "extra" for kw in node.keywords)
            extra_event = _extract_extra_event(node)

            if not has_extra:
                issues["missing_extra"].add((rel_path, node.lineno))
            if message and not EVENT_PATTERN.match(message):
                issues["freeform"].add((rel_path, node.lineno, message))
            if extra_event:
                if not EVENT_PATTERN.match(extra_event):
                    issues["invalid_event"].add((rel_path, node.lineno, extra_event))
                if message and extra_event != message:
                    issues["event_mismatch"].add((rel_path, node.lineno, message, extra_event))
    return issues


def _load_baseline() -> dict[str, set[tuple]]:
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {
        "freeform": {(d["path"], d["line"], d["message"]) for d in data["freeform"]},
        "missing_extra": {(d["path"], d["line"]) for d in data["missing_extra"]},
        "event_mismatch": {(d["path"], d["line"], d["message"], d["event"]) for d in data["event_mismatch"]},
        "invalid_event": {(d["path"], d["line"], d["event"]) for d in data["invalid_event"]},
    }


def test_structured_logger_events_snapshot() -> None:
    baseline = _load_baseline()
    current = _collect_issues()

    problems: list[str] = []
    for key in baseline:
        new_items = current[key] - baseline[key]
        resolved_items = baseline[key] - current[key]
        if new_items:
            problems.append(
                f"Nuove violazioni {key}: {sorted(new_items)!r}. " "Usa messaggi codice evento e passa sempre extra."
            )
        if resolved_items:
            problems.append(
                f"Violazioni rimosse non allineate al baseline {key}: {sorted(resolved_items)!r}. "
                "Aggiorna tests/fixtures/logging_events_baseline.json."
            )

    if problems:
        pytest.fail("\n".join(problems))
