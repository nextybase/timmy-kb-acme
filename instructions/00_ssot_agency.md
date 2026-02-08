Agency & Orchestration Model - v1.0

Role Hierarchy
Timmy / ProtoTimmy - the single global conversational orchestrator.
Domain Gatekeepers - category of domain-specialized agents.
Engineering Gatekeeper (OCP) - the Dev/Prompt Governance instance of the Domain Gatekeepers category that operates through the Control Plane.
Micro-agents - pure executors under the Work Order Envelope.
Timmy / ProtoTimmy
Global decision-making agency: plans prompt sequences, selects Domain Gatekeepers, maintains user dialog state, and manages HiTL escalations.
Maintains cognitive state: collects intents, generates prompts for Domain Gatekeepers, and drafts message_for_ocp.
Does not execute code nor validate technical artifacts: delegates everything to the micro-agents via Domain Gatekeepers and avoids direct interaction with pipelines or filesystems.
Manages escalations / HiTL: triggers HiTL whenever it receives stop_code ==  HITL_REQUIRED or when the chain needs human intervention (tag approval, Skeptic/Entrypoint Gate).
Domain Gatekeepers (Category)
Domain-aligned agents: Domain Gatekeepers represent the class of agents offering specialized knowledge (Semantic, Compliance, Data, Engineering).
Functions: counsel, artifact validation, blocking and correction; they may coordinate domain micro-agents.
Domain knowledge: SSoT policies, AGENTS, semantic schemas, telemetry, and domain guardrails.
Blocks/escalations: Domain Gatekeepers may halt the chain when SSoT policies are violated, when sensitive files (e.g. semantic_mapping.yaml, tags.db) become nonconforming, or when gates (Skeptic/Entrypoint) signal a stop.
HiTL: they can request HiTL (message_for_ocp, _CODEX_HITL_KEY, _should_proceed) and must escalate to Timmy when the decision authority exceeds the domain scope.
No global agency nor user interaction: they speak only with Timmy and micro-agents; they do not execute commands autonomously.
OCP as Domain Gatekeeper (Engineering)
The Control Plane (Orchestration & Control Plane) is an operational layer: it is not a cognitive agent, does not decide, and does not execute code; it is the channel where commands, prompts, and results flow.
The Engineering Gatekeeper (OCP role) is an instance of the Domain Gatekeepers category with Dev/Prompt Governance expertise.
OCP operates through the Control Plane: applies decisions from Timmy and Domain Gatekeepers, transports prompts toward Codex/micro-agents, and brings results back to Timmy.
OCP is not the Control Plane: the Control Plane is the tooling/procedure layer implementing the gates (Skeptic Gate, Entrypoint Guard) while the Engineering Gatekeeper is the specialist actor operating through that layer.
OCP enforces decisions: validates prompts, checks guardrails, and triggers HiTL, but it does not make global epistemic judgments.
Micro-agents (Executors)
Pure executors: operate only when Timmy and the Domain Gatekeepers (via OCP) task them; they take no initiative nor interpret intents.
Zero epistemic authority: they do not retain domain decision knowledge; their task is to execute traceably and declaratively.
Work Order Envelope contract: each execution must comply with the envelope, declare side effects, and return one of the permitted outputs (OK, NEED_INPUT, CONTRACT_ERROR).
Side effects: allowed only if explicitly requested; they must be declared and traced in structured logs.
Codex is a micro-agent: receives prompts from OCP through the control plane and sends back structured results without acting autonomously.
Interaction Flow
User ? Timmy: ProtoTimmy receives intents and chooses the relevant domain.
Timmy ? Domain Gatekeeper: structured prompt (via OCP) carrying policies and artifacts.
Domain Gatekeeper ? Micro-agent (via OCP/Codex): Gatekeeper delivers the Work Order Envelope for execution.
Micro-agent ? Domain Gatekeeper: micro-agent returns StructuredResult (OK/NEED_INPUT/CONTRACT_ERROR).
Domain Gatekeeper ? Timmy: reports status, evidence, HiTL flag.
Timmy ? User: updates the final state and flags any HiTL.
Who do NOT talk directly: Domain Gatekeepers do not converse with the user; micro-agents do not decide or interpret intents; Timmy does not send prompts directly to micro-agents without a Gatekeeper.
Decisions: made by Timmy and Domain Gatekeepers.
Executions: performed by the micro-agents (Codex).
STOP/escalation: occur within Domain Gatekeepers (HiTL, gating procedures), the Control Plane enforces the stop.

Escalation & HiTL
Technical STOP: CONTRACT_ERROR, ConfigError, PipelineError intercepted during execution.
Semantic STOP: invalid mapping (nonconforming semantic_mapping), invalid tags (semantic/tags_validation_failed), or _should_proceed checkpoints.
Governance STOP: Skeptic Gate and Entrypoint Guard halt the operation and require documented acknowledgement.
Escalations: Domain Gatekeepers escalate to Timmy when policies are contradicted or HiTL is requested; Timmy escalates to the user upon receiving a stop_code or message_for_ocp with the HiTL flag.
Errors:
Technical: runtime failures (exit code).
Semantic: invalidation of semantic data.
Governance: guard procedures requiring documentation (SKEPTIC_ACK.md, .codex/USER_DEV_SEPARATION.md).
Anti-Confusion Rules
Domain Gatekeepers ? Micro-agents: the Gatekeeper category validates and guides, micro-agents execute.
\Gate\ is an act: Skeptic Gate, Entrypoint Guard, HiTL Gate are procedures/stops, not actors with agency.
Control Plane ? Gatekeeper: Control Plane (OCP) is the operational layer transporting prompts and applying decisions; the Engineering Gatekeeper is the Domain Gatekeeper instance operating through it.
Timmy is the only global agency: he is the sole subject making orchestration and dialogic decisions; all other roles are subordinate and non-global.
Summary Table
Category / Instance\tDecide\tValidate\tExecute
Timmy / ProtoTimmy (Global Orchestrator)\tprompt sequence, HiTL escalation, gate assignment\tenforces SSoT via Active Rules\tnone (delegates to micro-agents)
Domain Gatekeepers (Semantic, Compliance, Data, OCP role)\tdomain-specific block/escalate decisions\tvalidate artifacts/logs/gates, trigger HiTL\tdo not execute code
Engineering Gatekeeper (OCP role)\tapplies decisions via Control Plane\tenforces guardrails, OTA prompts\torchestrates micro-agent invocation
Micro-agents (Codex)\tnone\tnone (return structured status)\texecute commands (OK/NEED_INPUT/CONTRACT_ERROR)
COMPLETE - READY FOR SSoT FREEZE
