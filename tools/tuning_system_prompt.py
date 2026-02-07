# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI control-plane per la lettura e l'aggiornamento del system prompt remoto."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from pipeline.logging_utils import get_structured_logger
from pipeline.system_prompt_api import (
    build_openai_client,
    load_remote_system_prompt,
    resolve_assistant_id,
    save_remote_system_prompt,
)

from tools.non_strict_step import non_strict_step

LOG = get_structured_logger("tools.tuning_system_prompt")

DEFAULT_PAYLOAD: Dict[str, Any] = {
    "status": "error",
    "mode": "control_plane",
    "slug": "",
    "action": "",
    "errors": [],
    "warnings": [],
    "artifacts": [],
    "returncode": 1,
    "timmy_beta_strict": "0",
}


def _build_payload(*, slug: str, action: str) -> Dict[str, Any]:
    payload = dict(DEFAULT_PAYLOAD)
    payload["slug"] = slug
    payload["action"] = action
    return payload


def _dump(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _resolve_assistant_id(args: argparse.Namespace) -> str:
    if args.assistant_id:
        return args.assistant_id
    return resolve_assistant_id()


def _load_prompt(client: Any, assistant_id: str, *, allow_beta_fallback: bool) -> Dict[str, Any]:
    data = load_remote_system_prompt(assistant_id, client, allow_beta_fallback=allow_beta_fallback)
    return {
        "status": "ok",
        "model": data.get("model"),
        "instructions": data.get("instructions"),
        "paths": {},
    }


def _save_prompt(
    client: Any,
    assistant_id: str,
    instructions: str,
    *,
    allow_beta_fallback: bool,
) -> Dict[str, Any]:
    save_remote_system_prompt(
        assistant_id,
        instructions,
        client,
        allow_beta_fallback=allow_beta_fallback,
    )
    return {
        "status": "ok",
        "instructions": instructions,
        "paths": {},
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Control-plane tool: gestione System Prompt remoto")
    parser.add_argument("--slug", default="dummy", help="Slug del client (per logging)")
    parser.add_argument(
        "--assistant-id",
        help="Override dell'assistant_id (default: OBNEXT_ASSISTANT_ID)",
    )
    parser.add_argument(
        "--mode",
        choices=("get", "set"),
        default="get",
        help="Operazione da eseguire (get: recupera, set: aggiorna)",
    )
    parser.add_argument(
        "--instructions",
        help="Prompt completo da inviare (richiesto con --mode set)",
    )
    parser.add_argument(
        "--allow-beta",
        action="store_true",
        help="Consente il fallback alle API beta (solo laddove documentato, non usato di default)",
    )
    args = parser.parse_args(argv)

    payload = _build_payload(slug=args.slug, action=f"system_prompt.{args.mode}")
    with non_strict_step("prompt_tuning", logger=LOG, slug=args.slug):
        try:
            assistant_id = _resolve_assistant_id(args)
            client = build_openai_client()
            allow_beta = args.allow_beta
            if args.mode == "get":
                result = _load_prompt(client, assistant_id, allow_beta_fallback=allow_beta)
            else:
                if not args.instructions:
                    raise ValueError("--instructions obbligatorio con --mode set")
                result = _save_prompt(
                    client,
                    assistant_id,
                    args.instructions,
                    allow_beta_fallback=allow_beta,
                )
            payload.update(result)
            payload["status"] = result.get("status", "ok")
            payload["returncode"] = 0
        except Exception as exc:
            LOG.warning(
                "tools.tuning_system_prompt.failed",
                extra={"slug": args.slug, "error": str(exc)},
            )
            payload["errors"].append(str(exc))
            payload["status"] = "error"
            payload["returncode"] = 1
        finally:
            _dump(payload)
    return payload["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
