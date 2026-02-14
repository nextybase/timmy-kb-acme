# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

# Perimetri dove una quota di "entropia" è ammessa (service/tooling/UX).
# Importante: tenere questa lista piccola e intenzionale.
SERVICE_ONLY_PREFIXES = (
    "src/ui/",
    "src/timmy_kb/ui/",
    "src/pipeline/drive/",  # capability opzionale/best-effort
)

# File service-only espliciti: utility/UI o best-effort non parte dell'Epistemic Envelope.
SERVICE_ONLY_FILES = {
    "src/pipeline/layout_summary.py",
    "src/pipeline/log_viewer.py",
    "src/timmy_kb/cli/retriever.py",
    "src/timmy_kb/cli/retriever_embeddings.py",
}

# File specifici esclusi (idealmente vuoto; usalo solo per eccezioni deliberate e temporanee).
EXCLUDED_FILES: set[str] = set()

# Pattern "except Exception: pass" (tolleriamo spazi e commenti inline)
RE_EXCEPT_EXCEPTION_PASS = re.compile(
    r"except\s+Exception\s*:\s*(?:#.*\n\s*)?pass\b", re.MULTILINE
)


@dataclass(frozen=True)
class Issue:
    path: str
    lineno: int
    col: int
    rule: str
    detail: str


def _iter_py_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if p.is_file()]


def _rel(p: Path) -> str:
    return p.relative_to(REPO_ROOT).as_posix()


def _is_service_only(rel: str) -> bool:
    return rel in SERVICE_ONLY_FILES or rel.startswith(SERVICE_ONLY_PREFIXES)


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def _parse_ast(src: str, filename: str) -> ast.AST | None:
    try:
        return ast.parse(src, filename=filename)
    except SyntaxError:
        return None


def _find_except_exception_pass(rel: str, src: str) -> list[Issue]:
    issues: list[Issue] = []
    for m in RE_EXCEPT_EXCEPTION_PASS.finditer(src):
        # best-effort lineno/col: contiamo righe fino a match start
        prefix = src[: m.start()]
        lineno = prefix.count("\n") + 1
        col = len(prefix.split("\n")[-1])
        issues.append(
            Issue(
                path=rel,
                lineno=lineno,
                col=col,
                rule="except-exception-pass",
                detail="Trovato 'except Exception: pass' (degradazione silenziosa vietata in Beta)",
            )
        )
    return issues


def _is_return_empty_list(node: ast.Return) -> bool:
    # return []
    v = node.value
    return isinstance(v, ast.List) and len(v.elts) == 0


def _find_return_empty_list_in_except(rel: str, tree: ast.AST) -> list[Issue]:
    issues: list[Issue] = []
    # Cerca return [] SOLO dentro blocchi except (fallback su errore)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_except(node):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and _is_return_empty_list(inner):
                issues.append(
                    Issue(
                        path=rel,
                        lineno=getattr(inner, "lineno", 1),
                        col=getattr(inner, "col_offset", 0),
                        rule="return-empty-list-in-except",
                        detail="Trovato 'return []' dentro except in modulo non service-only (fallback silenzioso su errore)",
                    )
                )
    return issues


def _is_broad_except(node: ast.ExceptHandler) -> bool:
    # except: ...
    if node.type is None:
        return True
    # except Exception / BaseException: ...
    if isinstance(node.type, ast.Name):
        return node.type.id in {"Exception", "BaseException"}
    # except (Exception, SomeError): ...
    if isinstance(node.type, ast.Tuple):
        for item in node.type.elts:
            if isinstance(item, ast.Name) and item.id in {"Exception", "BaseException"}:
                return True
    return False


def _import_targets_ui(mod: str | None) -> bool:
    return bool(mod) and (mod == "ui" or mod.startswith("ui."))


def _find_pipeline_imports_ui(rel: str, tree: ast.AST) -> list[Issue]:
    # Regola: pipeline non deve importare ui.*
    if not rel.startswith("src/pipeline/"):
        return []
    issues: list[Issue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _import_targets_ui(alias.name):
                    issues.append(
                        Issue(
                            path=rel,
                            lineno=getattr(node, "lineno", 1),
                            col=getattr(node, "col_offset", 0),
                            rule="pipeline-imports-ui",
                            detail=f"Import vietato da pipeline verso UI: import {alias.name}",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if _import_targets_ui(node.module):
                issues.append(
                    Issue(
                        path=rel,
                        lineno=getattr(node, "lineno", 1),
                        col=getattr(node, "col_offset", 0),
                        rule="pipeline-imports-ui",
                        detail=f"Import vietato da pipeline verso UI: from {node.module} import ...",
                    )
                )
    return issues


def test_entropy_guards() -> None:
    issues: list[Issue] = []

    for path in _iter_py_files(SRC_ROOT):
        rel = _rel(path)
        if rel in EXCLUDED_FILES:
            continue

        src = _read_text(path)
        tree = _parse_ast(src, filename=str(path))

        # 1) except Exception: pass (vietato fuori service-only)
        if not _is_service_only(rel):
            issues.extend(_find_except_exception_pass(rel, src))

        # 2) return [] come fallback su errore (vietato fuori service-only)
        if tree is not None and not _is_service_only(rel):
            issues.extend(_find_return_empty_list_in_except(rel, tree))

        # 3) pipeline importa ui.* (vietato sempre)
        if tree is not None:
            issues.extend(_find_pipeline_imports_ui(rel, tree))

    if issues:
        msg_lines = ["Entropy guards failed:"]
        for it in issues:
            msg_lines.append(f"- {it.path}:{it.lineno}:{it.col} [{it.rule}] {it.detail}")
        raise AssertionError("\n".join(msg_lines))
