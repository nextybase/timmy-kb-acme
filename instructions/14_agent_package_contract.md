# 14_agent_package_contract.md
**Status:** active
**Scope:** Agency Engine - structure and identity of the agents
**Authority:** `instructions/*` (normative SSoT)
**Precedence:** MANIFEST.md → instructions/* → code → docs/

---

## 1. Purpose of the document

This document defines the **mandatory structural contract** for every agent (micro-agents and gatekeepers) in the Timmy-KB ecosystem during **Beta 1.0**.

The contract specifies:
- how an agent is **identified**
- where an agent **lives in the repository**
- which **artifacts** it may produce
- which **behaviors are forbidden**

Any agent or implementation that violates a rule from this document is considered **non-compliant** in the system.

---

## 2. Definition of Agent Package

An **Agent Package** is the minimum valid unit representing an agent in the system.

An Agent Package consists of:
- a **formal identity**
- a **constrained repository layout**
- a set of **traceable runtime artifacts**

An agent **does not exist** in the system unless it is represented by a conformant Agent Package.

---

## 3. Agent identity (SSoT)

### 3.1 `agent_id`
Every agent must expose an `agent_id` that satisfies **all** the following conditions:

- it is **semantic and human-readable**
- it is **filesystem-safe**
- it is **immutable over time**
- it is **globally unique** within the repository

The `agent_id`:
- **must not be renamed**
- **must not have aliases**
- **must not be reused**

If an agent's role or purpose changes incompatibly, a **new agent with a new `agent_id`** must be created.

---

## 4. Repository placement (mandatory)

Each agent must live **exclusively** within the following path:

```
src/ai/<agent_id>/
```

Forbidden:
- spreading the same agent files across multiple directories
- defining agents solely via configuration or environment variables
- relying on undocumented naming conventions

---

## 5. `agent.yaml` - agent identity card

Every Agent Package must include the file:

```
src/ai/<agent_id>/agent.yaml
```

### 5.1 Role of the file
`agent.yaml` is the **Single Source of Truth** for:
- the agent's identity
- agent type
- ownership
- artifact policies

In **Beta 1.0**, `agent.yaml`:
- is **normative**
- may be **validated**
- is not necessarily consumed by the runtime for resolution

### 5.2 Obligations
- The file must exist.
- The file must be semantically aligned with the code.
- If the file is missing or invalid, the agent is **non-compliant**.

---

## 6. Minimum required structure

Each Agent Package must honor at least the following structure:

```
src/ai/<agent_id>/
├── agent.yaml
├── artifacts/
│   ├── latest.json
│   └── builds/
│       └── <build_id>/
│           └── build_manifest.json
```

### 6.1 Rules
- `artifacts/` is **append-only**
- `latest.json` is the only mutable file
- artifacts **must not be committed**
- no artifact may be overwritten

---

## 7. Build artifacts (`build_manifest.json`)

Every valid execution of an agent must produce a conformant **build_manifest**.

The `build_manifest.json`:
- is a **provenance artifact**
- attests to **what the agent performed**
- makes behavior **auditable**

The minimum required content is defined by the active build contract (versioned within the manifest schema).

---

## 8. Separation of identity, runtime, and data

A strict separation between the following domains is mandatory:

| Domain | Content |
| --- | --- |
| Identity | `agent.yaml` |
| Runtime | Python code |
| State | `artifacts/` |
| Operational data | workspace (`raw/`, `semantic/`, etc.) |

Forbidden:
- mixing runtime data and code
- inferring state from the presence or absence of undocumented files
- relying on implicit fallbacks

---

## 9. Relationship with the Agency Engine

This contract **does not change**:
- decision-making roles
- Prompt Chain
- gates, verdicts, HiTL
- Work Order Envelope

It **only defines**:
- the valid form of agents
- the minimum conditions for their technical existence

Decision rules remain defined in:
- `instructions/AGENTS.md`
- `instructions/02_prompt_chain_lifecycle.md`
- `instructions/03_gatekeepers_contracts.md`

---

## 10. Failure modes (non-negotiable)

The following cases constitute **system errors**:

- agent without `agent.yaml`
- ambiguous or renamed `agent_id`
- overwritten artifacts
- implicit fallbacks on path or identity
- state inferred without a manifest

In such conditions:
- execution **must stop**
- the error **must be explicit and traceable**

---

## 11. Closing note (Beta 1.0)

This contract aims to:
- reduce structural entropy
- make agents **governable objects**
- prepare for the Builder introduction without destructive migrations

Any deviation from this document is a **violation of the Beta 1.0 operational envelope**.
