# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]

# Perimetro blindato (CORE/CORE-adjacent) dove il contratto error/exit deve restare rigido.
GUARDED_FILES = (
    "src/pipeline/cli_runner.py",
    "src/pipeline/exceptions.py",
    "src/pipeline/drive/upload.py",
    "src/pipeline/vision_runner.py",
    "src/semantic/entities_runner.py",
    "src/timmy_kb/cli/tag_onboarding.py",
    "src/timmy_kb/cli/pre_onboarding.py",
    "src/timmy_kb/cli/kg_build.py",
    "src/timmy_kb/cli/semantic_headless.py",
    "src/timmy_kb/cli/raw_ingest.py",
)

# Allowlist chirurgica: solo catch-all deliberati con motivazione esplicita.
ALLOWLIST: dict[tuple[str, str | None], str] = {
    ("src/pipeline/cli_runner.py", "run_cli_orchestrator"): "ADR-007 firewall: unknown -> unexpected(99).",
    ("src/pipeline/exceptions.py", "_safe_file_repr"): "Safe stringification helper; no exit mapping effect.",
    ("src/pipeline/exceptions.py", "_mask_id"): "Safe masking helper; no exit mapping effect.",
    (
        "src/pipeline/drive/upload.py",
        "_delete_file_hard",
    ): "Drive API cleanup guard; 404 idempotency normalization.",
    (
        "src/pipeline/drive/upload.py",
        "upload_config_to_drive_folder",
    ): "Drive boundary normalization to DriveUploadError (operational failures).",
    (
        "src/pipeline/drive/upload.py",
        "create_drive_folder",
    ): "Drive boundary normalization with conservative drive-like heuristics.",
    (
        "src/pipeline/drive/upload.py",
        "delete_drive_file",
    ): "Drive delete boundary normalization to typed domain error.",
    (
        "src/pipeline/vision_runner.py",
        "_resolve_vision_mode",
    ): "Defensive settings/env read guard; typed config mapping.",
    ("src/pipeline/vision_runner.py", "_load_last_hash"): "Sentinel parsing guard; degrades to deterministic rerun.",
    (
        "src/semantic/entities_runner.py",
        "run_doc_entities_pipeline",
    ): "Typed domain mapping for known I/O/runtime boundaries; legacy config-load guard pending narrowing.",
    ("src/timmy_kb/cli/tag_onboarding.py", "_path_ref"): "Best-effort relative path rendering for evidence refs.",
    (
        "src/timmy_kb/cli/tag_onboarding.py",
        "run_nlp_to_db",
    ): "Entities integration boundary: missing component / known I/O mapped to PipelineError.",
    ("src/timmy_kb/cli/tag_onboarding.py", "tag_onboarding_main"): "Ledger recording fallback with typed re-raise.",
    ("src/timmy_kb/cli/tag_onboarding.py", "main"): "CLI top-level logging guard before re-raise.",
    ("src/timmy_kb/cli/pre_onboarding.py", "_path_ref"): "Best-effort relative path rendering for evidence refs.",
    (
        "src/timmy_kb/cli/pre_onboarding.py",
        "_is_local_only_mode",
    ): "Config read failure mapped to typed ConfigError for deterministic policy.",
    (
        "src/timmy_kb/cli/pre_onboarding.py",
        "_create_local_structure",
    ): "Best-effort local artifact metadata logging path; no contract re-mapping.",
    (
        "src/timmy_kb/cli/pre_onboarding.py",
        "ensure_local_workspace_for_ui",
    ): "UI bridge best-effort merge/upload logging; no exit contract mutation.",
    (
        "src/timmy_kb/cli/pre_onboarding.py",
        "_drive_phase",
    ): "Drive phase telemetry guards around non-critical artifact counting.",
    (
        "src/timmy_kb/cli/pre_onboarding.py",
        "pre_onboarding_main",
    ): "Ledger fallback path with typed re-raise in failure recording.",
    ("src/timmy_kb/cli/pre_onboarding.py", "main"): "CLI top-level logging guard before re-raise.",
    ("src/timmy_kb/cli/kg_build.py", "kg_build_main"): "KG build logging guard; typed errors propagated by runner.",
    ("src/timmy_kb/cli/kg_build.py", "main"): "CLI top-level logging guard before re-raise.",
    (
        "src/timmy_kb/cli/semantic_headless.py",
        "run_semantic_headless",
    ): "Defensive headless context guard returning deterministic result envelope.",
    ("src/timmy_kb/cli/semantic_headless.py", "main"): "Top-level deterministic exit mapping (2/99/130).",
    ("src/timmy_kb/cli/raw_ingest.py", "_path_ref"): "Best-effort relative path rendering for evidence refs.",
    ("src/timmy_kb/cli/raw_ingest.py", "run_raw_ingest"): "Ledger fallback path with typed re-raise.",
    ("src/timmy_kb/cli/raw_ingest.py", None): "Module-level __main__ fallback for deterministic process exit (99/130).",
}

DISALLOWED_EXCEPT_TYPES = {"Exception", "BaseException"}
DISALLOWED_REWRAP_TARGETS = {"PipelineError"}


@dataclass(frozen=True)
class Violation:
    relpath: str
    lineno: int
    col: int
    func: str | None
    kind: str
    snippet: str


def _iter_guarded_files() -> Iterable[Path]:
    for rel in GUARDED_FILES:
        path = REPO_ROOT / rel
        if path.exists():
            yield path


def _handler_type_name(handler: ast.ExceptHandler) -> str:
    if handler.type is None:
        return "BARE"
    if isinstance(handler.type, ast.Name):
        return handler.type.id
    if isinstance(handler.type, ast.Attribute):
        return handler.type.attr
    return type(handler.type).__name__


def _enclosing_function_name(stack: list[ast.AST]) -> str | None:
    for node in reversed(stack):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return None


def _is_allowlisted(relpath: str, func: str | None) -> bool:
    return (relpath, func) in ALLOWLIST or (relpath, None) in ALLOWLIST


def _get_line(src: str, lineno: int) -> str:
    lines = src.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


def _handler_raises_disallowed_rewrap(handler: ast.ExceptHandler) -> bool:
    body_module = ast.Module(body=handler.body, type_ignores=[])
    for node in ast.walk(body_module):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc
        if isinstance(exc, ast.Call):
            func = exc.func
            if isinstance(func, ast.Name) and func.id in DISALLOWED_REWRAP_TARGETS:
                return True
            if isinstance(func, ast.Attribute) and func.attr in DISALLOWED_REWRAP_TARGETS:
                return True
        if isinstance(exc, ast.Name) and exc.id in DISALLOWED_REWRAP_TARGETS:
            return True
    return False


def test_no_catchall_except_in_core() -> None:
    violations: list[Violation] = []

    for path in _iter_guarded_files():
        relpath = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        src = path.read_text(encoding="utf-8")

        try:
            tree = ast.parse(src, filename=relpath)
        except SyntaxError as exc:
            raise AssertionError(f"SyntaxError while parsing {relpath}: {exc}") from exc

        stack: list[ast.AST] = []

        class Visitor(ast.NodeVisitor):
            def generic_visit(self, node: ast.AST) -> None:
                stack.append(node)
                super().generic_visit(node)
                stack.pop()

            def visit_Try(self, node: ast.Try) -> None:
                for handler in node.handlers:
                    kind = _handler_type_name(handler)
                    func = _enclosing_function_name(stack)

                    if kind == "KeyboardInterrupt":
                        continue

                    if kind == "BARE":
                        if not _is_allowlisted(relpath, func):
                            violations.append(
                                Violation(
                                    relpath=relpath,
                                    lineno=handler.lineno or node.lineno,
                                    col=handler.col_offset or 0,
                                    func=func,
                                    kind="bare-except",
                                    snippet=_get_line(src, handler.lineno or node.lineno),
                                )
                            )
                        continue

                    if kind in DISALLOWED_EXCEPT_TYPES and not _is_allowlisted(relpath, func):
                        violations.append(
                            Violation(
                                relpath=relpath,
                                lineno=handler.lineno or node.lineno,
                                col=handler.col_offset or 0,
                                func=func,
                                kind=f"except-{kind}",
                                snippet=_get_line(src, handler.lineno or node.lineno),
                            )
                        )
                    if _handler_raises_disallowed_rewrap(handler) and not _is_allowlisted(relpath, func):
                        violations.append(
                            Violation(
                                relpath=relpath,
                                lineno=handler.lineno or node.lineno,
                                col=handler.col_offset or 0,
                                func=func,
                                kind="rewrap-PipelineError",
                                snippet=_get_line(src, handler.lineno or node.lineno),
                            )
                        )

                self.generic_visit(node)

        Visitor().visit(tree)

    if violations:
        has_rewrap_pipeline_error = any(v.kind == "rewrap-PipelineError" for v in violations)
        lines = [
            "Catch-all or entropic rewrap detected in guarded CORE perimeter (disallowed).",
            "Fix: narrow exception types or add explicit allowlist entry with reason and ADR reference.",
            "",
        ]
        if has_rewrap_pipeline_error:
            lines.append("Prefer: propagate typed errors; for unexpected rely on ADR-007 (exit 99).")
            lines.append("")
        for violation in violations:
            where = f"{violation.relpath}:{violation.lineno}:{violation.col}"
            in_func = f" (in {violation.func}())" if violation.func else ""
            lines.append(f"- {where}{in_func} -> {violation.kind} :: {violation.snippet}")
        lines.append("")
        lines.append("Allowlist entries:")
        for (rel, func), reason in sorted(ALLOWLIST.items()):
            suffix = f"::{func}" if func else ""
            lines.append(f"  - {rel}{suffix} -> {reason}")
        raise AssertionError("\n".join(lines))
