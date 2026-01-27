from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DummyPolicy:
    mode: str  # "smoke" | "deep"
    strict: bool  # Beta: True
    ci: bool  # esecuzione in CI
    allow_downgrade: bool = False
    require_registry: bool = True
