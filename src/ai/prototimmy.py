# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from pipeline.exceptions import ConfigError
from pipeline.settings import Settings

from .assistant_registry import resolve_ocp_executor_config, resolve_planner_config, resolve_prototimmy_config
from .responses import run_text_model
from .types import AssistantConfig


@dataclass(frozen=True)
class ProtoTimmyStepResult:
    role: str
    model: str
    prompt: str
    output: str
    raw: Any | None = None


@dataclass(frozen=True)
class ProtoTimmyChainResult:
    ok: bool
    steps: List[ProtoTimmyStepResult] = field(default_factory=list)
    error: Optional[str] = None
    workspace_slug: Optional[str] = None


def _load_settings(repo_root_dir: Optional[str] = None) -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    root = Path(repo_root_dir) if repo_root_dir else repo_root
    return Settings.load(root)


def _proto_ping_prompt() -> str:
    return "Ping di test da timmy-kb-acme (protoTimmy). Rispondi solo con la parola 'pong'."


def _proto_chain_prompt() -> str:
    return "Test di integrazione. Genera una breve frase che inizi con " "'PROTO:' e non aggiungere spiegazioni."


def _planner_prompt(proto_text: str) -> str:
    return (
        "Test di integrazione Planner.\n"
        "Hai ricevuto questo input da protoTimmy:\n"
        f"{proto_text}\n\n"
        "Aggiungi alla fine della stringa esattamente ' PLANNER_OK' "
        "e restituisci SOLO la stringa risultante, senza spiegazioni."
    )


def _ocp_prompt(planner_text: str) -> str:
    return (
        "Test di integrazione OCP Executor.\n"
        "Hai ricevuto questo input dal Planner Assistant"
        f"{planner_text}\n\n"
        "Aggiungi alla fine della stringa esattamente ' OCP_OK' "
        "e restituisci SOLO la stringa risultante, senza spiegazioni."
    )


def _build_prototimmy_invocation(
    cfg: AssistantConfig,
    *,
    component: str,
    operation: str,
    step: str | None = None,
    request_tag: str | None = None,
) -> dict[str, Any]:
    invocation: dict[str, Any] = {
        "component": component,
        "operation": operation,
        "assistant_id": cfg.assistant_id,
        "strict_output": cfg.strict_output,
        "use_kb": cfg.use_kb,
    }
    if step:
        invocation["step"] = step
    if request_tag:
        invocation["request_tag"] = request_tag
    return invocation


def run_prototimmy_ping(*, repo_root_dir: Optional[str] = None) -> ProtoTimmyStepResult:
    settings = _load_settings(repo_root_dir)
    cfg = resolve_prototimmy_config(settings)
    prompt = _proto_ping_prompt()
    resp = run_text_model(
        model=cfg.model,
        messages=[{"role": "user", "content": prompt}],
        invocation=_build_prototimmy_invocation(
            cfg,
            component="prototimmy",
            operation="prototimmy.ping",
            request_tag="prototimmy_ping",
        ),
    )
    text = resp.text.strip()
    if text.lower() != "pong":
        raise ConfigError(f"Ping protoTimmy non valido: {text!r}")
    return ProtoTimmyStepResult(role="prototimmy", model=cfg.model, prompt=prompt, output=text, raw=resp.raw)


def run_prototimmy_chain(
    *,
    repo_root_dir: Optional[str] = None,
    workspace_slug: Optional[str] = None,
) -> ProtoTimmyChainResult:
    settings = _load_settings(repo_root_dir)
    proto_cfg = resolve_prototimmy_config(settings)
    planner_cfg = resolve_planner_config(settings)
    ocp_cfg = resolve_ocp_executor_config(settings)

    steps: List[ProtoTimmyStepResult] = []

    try:
        proto_prompt = _proto_chain_prompt()
        proto_resp = run_text_model(
            model=proto_cfg.model,
            messages=[{"role": "user", "content": proto_prompt}],
            invocation=_build_prototimmy_invocation(
                proto_cfg,
                component="prototimmy",
                operation="prototimmy.chain.prototimmy",
                step="prototimmy",
                request_tag="prototimmy_chain_proto",
            ),
        )
        proto_out = proto_resp.text.strip()
        steps.append(
            ProtoTimmyStepResult(
                role="prototimmy",
                model=proto_cfg.model,
                prompt=proto_prompt,
                output=proto_out,
                raw=proto_resp.raw,
            )
        )
        if not proto_out.startswith("PROTO:"):
            raise ConfigError("Risposta protoTimmy non conforme (manca prefix PROTO:).")

        planner_prompt = _planner_prompt(proto_out)
        planner_resp = run_text_model(
            model=planner_cfg.model,
            messages=[{"role": "user", "content": planner_prompt}],
            invocation=_build_prototimmy_invocation(
                planner_cfg,
                component="prototimmy",
                operation="prototimmy.chain.planner",
                step="planner",
                request_tag="prototimmy_chain_planner",
            ),
        )
        planner_out = planner_resp.text.strip()
        steps.append(
            ProtoTimmyStepResult(
                role="planner",
                model=planner_cfg.model,
                prompt=planner_prompt,
                output=planner_out,
                raw=planner_resp.raw,
            )
        )
        if not planner_out.endswith("PLANNER_OK"):
            raise ConfigError("Risposta Planner non conforme (manca PLANNER_OK).")

        ocp_prompt = _ocp_prompt(planner_out)
        ocp_resp = run_text_model(
            model=ocp_cfg.model,
            messages=[{"role": "user", "content": ocp_prompt}],
            invocation=_build_prototimmy_invocation(
                ocp_cfg,
                component="prototimmy",
                operation="prototimmy.chain.ocp_executor",
                step="ocp_executor",
                request_tag="prototimmy_chain_ocp",
            ),
        )
        ocp_out = ocp_resp.text.strip()
        steps.append(
            ProtoTimmyStepResult(
                role="ocp_executor",
                model=ocp_cfg.model,
                prompt=ocp_prompt,
                output=ocp_out,
                raw=ocp_resp.raw,
            )
        )
        if not ocp_out.endswith("OCP_OK"):
            raise ConfigError("Risposta OCP non conforme (manca OCP_OK).")

        return ProtoTimmyChainResult(ok=True, steps=steps, workspace_slug=workspace_slug)
    except Exception as exc:
        return ProtoTimmyChainResult(ok=False, steps=steps, error=str(exc), workspace_slug=workspace_slug)
