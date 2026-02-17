# SPDX-License-Identifier: GPL-3.0-or-later
'"""Verifica che i facade pubblici non importino moduli interni proibiti."""'

from __future__ import annotations

import ast
from pathlib import Path

FACADES = [
    "src/timmy_kb/cli/pre_onboarding.py",
    "src/timmy_kb/cli/tag_onboarding.py",
    "src/timmy_kb/cli/semantic_onboarding.py",
    "tools/gen_vision_yaml.py",
]
FACADES += list(Path("src/ui").rglob("*.py"))
FACADES += list(Path("src/api").rglob("*.py"))

# Moduli internI proibiti; i facade devono usare only `pipeline.context`,
# `pipeline.exceptions` o `semantic.api`.
BLACKLIST = (
    "pipeline.drive",
    "semantic.vision_provision",
    "semantic.vision_api",
)

UI_FORBIDDEN_PREFIXES = (
    "timmy_kb.cli",
    "pipeline.drive.",
    "pipeline.drive.client",
    "pipeline.drive.download",
    "pipeline.drive.upload",
    "ai.client_factory",
    "ai.providers",
    "semantic.vision_provision",
    "semantic.pdf_utils",
    "semantic.vision_utils",
    "semantic.validation",
)

UI_CLI_IMPORT_EXCEPTIONS = {
    Path("src/ui/services/control_plane.py").as_posix(),
}


def _normalize(module: str | None) -> str:
    return module or ""


def test_facade_imports_only_public_surface():
    errors: list[str] = []
    for path in FACADES:
        if isinstance(path, Path):
            filepath = path
        else:
            filepath = Path(path)
        try:
            source = filepath.read_text(encoding="utf-8")
        except Exception:
            continue
        tree = ast.parse(source, filename=str(filepath))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = _normalize(alias.name)
                    if any(mod.startswith(bad) for bad in BLACKLIST):
                        errors.append(
                            f"{filepath}:{mod} importa '{mod}' (use the public pipeline.{mod.split('.',1)[0]} facade)"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = _normalize(node.module)
                if any(module.startswith(bad) for bad in BLACKLIST):
                    errors.append(f"{filepath}:{module} importa '{module}' (use the public facade)")
    assert not errors, "\n".join(errors)


def test_ui_imports_use_only_public_surfaces():
    errors: list[str] = []
    ui_root = Path("src/ui")
    for path in ui_root.rglob("*.py"):
        path_key = path.as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = _normalize(alias.name)
                    if mod.startswith("timmy_kb.cli") and path_key in UI_CLI_IMPORT_EXCEPTIONS:
                        continue
                    if any(mod.startswith(prefix) for prefix in UI_FORBIDDEN_PREFIXES):
                        errors.append(
                            f"{path}:{mod} imports '{mod}' "
                            "(UI must stay within facades; see .codex/USER_DEV_SEPARATION.md)"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = _normalize(node.module)
                if module.startswith("timmy_kb.cli") and path_key in UI_CLI_IMPORT_EXCEPTIONS:
                    continue
                if any(module.startswith(prefix) for prefix in UI_FORBIDDEN_PREFIXES):
                    errors.append(
                        f"{path}:{module} imports '{module}' "
                        "(UI must stay within facades; see .codex/USER_DEV_SEPARATION.md)"
                    )
                if node.level == 0 and module and not module.startswith("ui"):
                    for alias in node.names:
                        if alias.name.startswith("_"):
                            errors.append(
                                f"{path}:{module} imports private symbol '{alias.name}' "
                                "(UI must not import cross-package _private symbols)"
                            )
    assert not errors, "\n".join(errors)
