# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper condivisi per interrogare e aggiornare il system prompt remoto."""

from __future__ import annotations

from typing import Any, Dict

from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.import_utils import import_from_candidates
from pipeline.logging_utils import get_structured_logger

LOG = get_structured_logger("pipeline.system_prompt_api")
_CANDIDATES = [
    "ai.client_factory:make_openai_client",
    "..ai.client_factory:make_openai_client",
]


def resolve_assistant_id() -> str:
    """Ritorna l'assistant_id dal SSoT dell'ambiente."""
    assistant_id = get_env_var("OBNEXT_ASSISTANT_ID", default=None)
    if not assistant_id:
        raise ConfigError("Assistant ID mancante (env: OBNEXT_ASSISTANT_ID).")
    return assistant_id


def build_openai_client() -> Any:
    """Costruisce il client OpenAI usando SOLO il factory del progetto (Beta: no fallback)."""
    try:
        factory = import_from_candidates(
            _CANDIDATES,
            package=__package__,
            description="make_openai_client",
            logger=LOG,
        )
        return factory()
    except ImportError as exc:
        raise ConfigError("Factory OpenAI mancante: make_openai_client non risolto (Beta: no fallback).") from exc


def _retrieve_assistant(client: Any, assistant_id: str) -> Any:
    assistants = getattr(client, "assistants", None)
    if assistants is not None and hasattr(assistants, "retrieve"):
        return assistants.retrieve(assistant_id)

    raise ConfigError("Client OpenAI non espone l'API assistants.")


def _update_assistant(
    client: Any,
    assistant_id: str,
    *,
    instructions: str,
) -> Any:
    assistants = getattr(client, "assistants", None)
    if assistants is not None and hasattr(assistants, "update"):
        return assistants.update(assistant_id, instructions=instructions)

    raise ConfigError("Client OpenAI non espone l'API assistants.")


def load_remote_system_prompt(
    assistant_id: str,
    client: Any,
) -> Dict[str, str]:
    """Recupera modello e istruzioni dell'assistant in modo sicuro."""
    assistant = _retrieve_assistant(client, assistant_id)
    model = getattr(assistant, "model", "") or ""
    instructions = getattr(assistant, "instructions", "") or ""
    return {
        "model": model,
        "instructions": instructions,
    }


def save_remote_system_prompt(
    assistant_id: str,
    instructions: str,
    client: Any,
) -> None:
    """Aggiorna le istruzioni dell'assistant in modo control-plane."""
    _update_assistant(
        client,
        assistant_id,
        instructions=instructions,
    )


__all__ = [
    "resolve_assistant_id",
    "build_openai_client",
    "load_remote_system_prompt",
    "save_remote_system_prompt",
]
