# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AssistantConfig:
    """Configurazione risolta per un assistant/model OpenAI."""

    model: str
    assistant_id: str
    assistant_env: str
    use_kb: Optional[bool] = None
    strict_output: Optional[bool] = None


@dataclass(frozen=True)
class ResponseText:
    """Output testuale della Responses API."""

    model: str
    text: str
    raw: Any


@dataclass(frozen=True)
class ResponseJson:
    """Output JSON parsato dalla Responses API."""

    model: str
    data: Dict[str, Any]
    raw_text: str
    raw: Any
