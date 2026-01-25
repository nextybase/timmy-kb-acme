# 07 - Modular Gate Checklists (Engineering Gatekeeper / OCP-plane)

**Status:** ACTIVE
**Authority:** Operational checklist, subordinate to SSoT
**Scope:** checklist cognitive e operative per supportare decisioni
PASS / PASS_WITH_CONDITIONS / BLOCK sulle transizioni di stato del workspace.

Questo documento **non definisce** binding, stati o semantica di avanzamento.
Fornisce **strumenti di valutazione** per l'Engineering Gatekeeper (AI),
che opera esclusivamente tramite OCP-plane.

Riferimenti normativi:
- `instructions/05_pipeline_state_machine.md`
- `instructions/06_promptchain_workspace_mapping.md`
- `instructions/08_gate_evidence_and_retry_contract.md`
- `instructions/02_prompt_chain_lifecycle.md`

---

## Principi Globali (Beta 1.0)
- Ogni modulo corrisponde a **una singola transizione di stato**.
- Le checklist **non producono stato**: supportano l'emissione di un Decision Record.
- Il Gatekeeper:
  - non esegue azioni,
  - non modifica artefatti,
  - valuta solo **evidenze verificabili**.
- Ogni verdict (PASS / BLOCK / FAIL / PASS_WITH_CONDITIONS) deve essere
  formalizzato tramite **Decision Record append-only**.
- L'applicabilità dei gate per ciascuna transizione è definita in
  `instructions/06_promptchain_workspace_mapping.md`.
- Tutti i gate MUST essere conformi a `instructions/10_runtime_strict_contract_beta.md`; ogni violazione implica BLOCK.

---

## Modulo 1 - `WORKSPACE_BOOTSTRAP → SEMANTIC_INGEST`

**Gate richiesti:**
- Evidence Gate (layout & artefatti)
- Skeptic Gate (OCP supervision)

**Evidence anchors (minimi):**
- Directory `raw/`, `config/`, `semantic/`, ledger
- `config/config.yaml`
- Log: `pre_onboarding.workspace.created`, `context.config.bootstrap`

**Checklist:**
1. **Layout integrity**
   WorkspaceLayout ha creato tutte le directory canoniche?
2. **Config validity**
   `config/config.yaml` esiste ed è leggibile?
3. **Scope safety**
   Tutti i path sono validati via `ensure_within*`?
4. **Ledger readiness**
   Il ledger è scrivibile (condizione necessaria per Decision Record)?
5. **Stop / BLOCK**
   `WorkspaceLayoutInvalid` o `WorkspaceNotFound` ⇒ BLOCK
   Azione attesa: rigenerare workspace (`bootstrap_client_workspace`).

---

## Modulo 2 - `SEMANTIC_INGEST → FRONTMATTER_ENRICH`

**Gate richiesti:**
- Evidence Gate
- Skeptic Gate (OCP)

**Evidence anchors:**
- `semantic/tags.db`
- `tags_reviewed.yaml`
- Raw PDFs presenti in `raw/`

**Checklist:**
1. **Artefatti semantici**
   `semantic/tags.db` esiste ed è coerente?
2. **Checkpoint HiTL**
   `tags_reviewed.yaml` presente e valido?
3. **Input readiness**
   `raw/` contiene PDF validi (condizione di azione, non di stato)?
4. **Scope safety**
   Artefatti sotto layout canonico?
5. **Stop / BLOCK**
   Tagging incompleto o input assente ⇒ BLOCK
   Azione attesa: caricare PDF o ripetere ingest.

---

## Modulo 3 - `FRONTMATTER_ENRICH → VISUALIZATION_REFRESH`

**Gate richiesti:**
- Evidence Gate
- Skeptic Gate (OCP)

**Evidence anchors:**
- `book/*.md` (draft)
- Log `semantic.book.frontmatter`

**Checklist:**
1. **Frontmatter generation**
   I markdown draft sono stati prodotti?
2. **Semantic coherence**
   Frontmatter allineato a `semantic/tags.db`?
3. **Scope safety**
   Conversione effettuata tramite API pubbliche e path-safe?
4. **Observability**
   Eventi di errore non silenziati?
5. **Stop / BLOCK**
   Incoerenza semantica ⇒ BLOCK
   Azione attesa: correggere mapping/tag.

---

## Modulo 4 - `VISUALIZATION_REFRESH → PREVIEW_READY`

**Gate richiesti:**
- Evidence Gate
- Skeptic Gate (OCP)

**Evidence anchors:**
- `semantic/kg.tags.*`
- Draft finali `README.md`, `SUMMARY.md`

**Checklist:**
1. **KG generation**
   Artefatti di visualizzazione presenti e aggiornati?
2. **Preview completeness**
   README/SUMMARY coerenti con KG?
3. **Scope safety**
   Generazione avvenuta solo su path canonici?
4. **Observability**
   Log di generazione completi e non contraddittori?
5. **Stop / BLOCK**
   Preview incompleta o KG incoerente ⇒ BLOCK
   Azione attesa: rigenerare visualizzazione.

---

## Modulo 5 - `PREVIEW_READY → COMPLETE`

**Gate richiesti:**
- QA Gate
- Evidence Gate
- Skeptic Gate (OCP)

**Evidence anchors:**
- Artefatti finali in `book/` e `semantic/`
- Report QA
- `logs/qa_passed.json` (CORE-GATE)

**Checklist:**
1. **Artefatti finali**
   Markdown e KG presenti e path-safe?
2. **QA results**
   QA Gate ha prodotto verdict PASS?
   Se FAIL: `stop_code = QA_GATE_FAILED`
3. **Consistency**
   Nessuna discrepanza tra preview e output finale?
4. **Observability**
   Tutti i verdict sono tracciati?
5. **Stop / BLOCK / FAIL**
   QA failure ⇒ FAIL
   Azione attesa: correzione e nuova run.

---

## Regole di Chiusura
- Ogni modulo produce **esattamente un verdict**.
- Ogni verdict produce **un Decision Record**.
- Nessun modulo può:
  - dedurre stato,
  - aggiornare stato,
  - regredire stato.
- In assenza di Decision Record, **la transizione non è avvenuta**.
