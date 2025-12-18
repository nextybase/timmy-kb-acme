# SPDX-License-Identifier: GPL-3.0-only
## ROLE: Codex / PHASE: Closure

Scopo: formalizzare il packet di chiusura (Prompt N+1) e il successivo Skeptic Gate N+1′ che ogni Prompt Chain deve attraversare prima di considerarsi completata.

## Prompt N+1 (Closure Packet)
- ruolo: `Codex`
- output atteso:
  1. riepilogo delle modifiche e dei motivi di sicurezza,
  2. verifica delle policy `.codex/AGENTS.md`, `.codex/PROMPTS.md`, `.codex/WORKFLOWS.md`,
  3. elenco test automatizzati eseguiti + log di Skeptic Gate,
  4. nota conclusiva “Chain chiusa” in italiano.

## Skeptic Gate N+1′
- ruolo: `OCP`
- verifica: diff contro branch base, guardrail su file sensibili (`src/ai/resolution.py`, `pipeline/exceptions.py` etc.), patterns `Optional`, `return None`, `ConfigError`.
- non implementa: nuova logica, refactor progettuali, negoziazioni di scala temporale.

- [ ] Scope confermato (target files controllati)
- [ ] Evidenze verificate (log/test/pattern)
- [ ] Invarianti UX confermate (message invariati, ConfigError compatibili)
- [ ] Guardrail dichiarati vs reali documentati (SKEPTIC_ACK.md o test aggiornati)
- [ ] Rischi realistici enumerati
- [ ] Strategia di rollback pronta

## Esiti
- PASS → Prompt Chain chiusa.
- PASS CON RISERVA → non chiuso; richiede nuovo Prompt N+1 prima di merge.
- FAIL → HiTL necessario.

## Regola vincolante
Una Prompt Chain è chiusa solo dopo PASS del Skeptic Gate N+1′.

## Riferimenti
- `.codex/PROMPTS.md`
- `.codex/WORKFLOWS.md`
- `.codex/AGENTS.md`
- `docs/runbook_codex.md`
- `SKEPTIC_ACK.md`

## Nota ACK / skip
Skeptic Gate può essere ACKato aggiornando `tests/**` o `SKEPTIC_ACK.md`. In assenza di diff context (es. run locale) il gate stampa “SKIPPED”.
