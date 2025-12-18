# SPDX-License-Identifier: GPL-3.0-only
'"""Verifica che i facade pubblici non importino moduli interni proibiti."""'

from __future__ import annotations

import ast
from pathlib import Path

FACADES = [
    "src/timmy_kb/cli/pre_onboarding.py",
    "src/timmy_kb/cli/tag_onboarding.py",
    "src/timmy_kb/cli/semantic_onboarding.py",
    "src/onboarding_full.py",
    "src/tools/gen_vision_yaml.py",
]
FACADES += list(Path("src/ui").rglob("*.py"))
FACADES += list(Path("src/api").rglob("*.py"))

# Moduli internI proibiti; i facade devono usare only `pipeline.context`,
# `pipeline.exceptions` o `semantic.api`.
BLACKLIST = (
    "pipeline.drive",
    "pipeline.drive_utils",
    "pipeline.github",
    "pipeline.github_utils",
    "semantic.vision_provision",
    "semantic.vision_api",
)


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
