# Guida all'uso di Codex in VS Code e Prompt Chain

## 1. Prompt Chain: il modo prioritario di usare Codex

La modalità principale e consigliata per usare Codex nel progetto NeXT/Timmy-KB è tramite la **Prompt Chain** orchestrata da l’**OCP (OrchestratoreChainPrompt)**.

L’idea di base:
- L’utente (tu) definisce lo scopo del lavoro.
- L’OCP traduce questo obiettivo nel protocollo Planner → OCP → Codex → OCP → Planner, con Phase 0 (analisi read-only), Phase 1..N (micro-PR operativi) e Prompt N+1 (QA finale e riepilogo in italiano).
- Ogni prompt viene inviato a Codex **uno alla volta**, come micro-PR con memo Active Rules, QA intermedia e finale, e risposte sempre in italiano, mentre la documentazione di riferimento resta in inglese.

### 1.1 Come funziona la Prompt Chain

1. **Prompt 0 – Onboarding (Phase 0)**
   - Fornisce il contesto generale (repo, obiettivi, regole attive) senza toccare il filesystem.
   - Ricorda a Codex di leggere gli SSoT chiave: `.github/codex-instructions.md`, `docs/PromptChain_spec.md`, `docs/AGENTS_INDEX.md`, gli `AGENTS.md` di area e `.codex/PROMPTS.md`.
   - Definisce l’obiettivo della catena (es. refactor, feature, hardening QA) e conferma il piano operativo con risposta in italiano.

2. **Prompt 1/2 – Analisi e allineamento (Phase 0)**
   - Codex lavora in sola lettura, mappa dipendenze/rischi e non produce diff né lancia QA.
   - L’OCP mostra il riepilogo all’utente (HiTL) per confermare o restringere lo scope prima di passare ai prompt operativi.

3. **Prompt operativi (3..N) – Phase 1..N**
   - Ogni prompt ha uno scope ristretto: una modifica singola, un refactor piccolo, un fix mirato.
   - I prompt operativi iniziano con il memo Active Rules (path safety, micro-PR, zero side effects, QA intermedia `pytest -q -k "not slow"`, lingua italiana) definito in `.codex/PROMPTS.md`.
   - In ciascuno step Codex prepara la patch, applica il pre-check statico (no I/O raw/import privati/path hardcoded/patch non atomiche), esegue QA intermedia, e fornisce diff/report/risultato in italiano.

4. **Prompt finale di QA (Prompt N+1)**
   - Esegue la QA completa: `pre-commit run --all-files` e `pytest -q`, documenta eventuali retry (fino a 10) e termina con una one-line commit summary in italiano.
   - Dopo due tentativi falliti Codex chiede istruzioni (HiTL).

5. **Codex Smoke Chain**
   - È una mini-catena diagnostica che simula il comportamento di Codex senza modificare i file.
   - Serve per verificare che: le Regole Attive siano comprese, la QA venga interpretata correttamente, il pre-check statico sia attivo e la Language Policy (italiano) sia rispettata.
   - Può essere usata come “test rapido” della Prompt Chain dopo modifiche ai meta-file.

### 1.2 Quando usare la Prompt Chain

Usa la Prompt Chain come **modalità predefinita** quando:
- devi fare refactor su aree complesse (UI, pipeline, semantic);
- devi allineare codice e documentazione alle regole di NeXT (Probabilismo, HiTL, SSoT);
- vuoi interventi incrementali, controllati, con QA integrata;
- stai lavorando su task che coinvolgono più file o più servizi.

In pratica: quando il lavoro **non è banale**, la Prompt Chain è il modo migliore per usare Codex in modo sicuro, tracciabile e coerente.

---

## 2. Uso diretto di Codex in VS Code

Oltre alla Prompt Chain orchestrata, puoi usare Codex direttamente in VS Code attraverso l’estensione dedicata.

### 2.1 Modalità di Codex

1. **Chat**
   - Conversazione pura.
   - Utile per brainstorming, piani di refactor, chiarimenti architetturali.
   - Non esegue comandi, non applica patch.

2. **Agent (consigliato)**
   - Legge i file, propone patch, esegue comandi nella working directory.
   - È la modalità standard per sviluppo guidato da l’agente su questo repo.

3. **Agent (Full Access)**
   - Include accesso alla rete e meno prompt di conferma.
   - Va usato **solo** su branch dedicati e per task ad alto sforzo (migrazioni massicce, rigenerazione documentazione), con attenzione particolare alla sicurezza.

### 2.2 Setup di base

- Installa l’estensione Codex in VS Code dal Marketplace.
- Accedi con account ChatGPT (Plus/Pro/Team/Enterprise) o API key.
- Su Windows è consigliato l’uso di WSL; macOS e Linux sono pienamente supportati.

Config consigliata in `~/.codex/config.toml` (semplificata):

```toml
approval_mode = "agent"   # agent | chat | full

[mcp_servers.files]
type = "filesystem"
root = "/percorso/al/workspace/timmy-kb-acme"  # adattare al proprio ambiente
```

Questa configurazione espone a Codex solo il filesystem del workspace, mantenendo il principio di **accesso minimo**.

---

## 3. Tecniche di prompting per usare Codex in modo efficiente

Per ottenere il massimo da Codex (sia in Chat che in Agent), alcune tecniche di prompting aiutano moltissimo.

### 3.1 Prompt orientati al contesto

- Indica sempre **dove** lavorare: file, directory, servizi.
  - Esempio:
    *"Lavora su `src/ui/preflight.py` e spiega prima il flusso, poi proponi al massimo 2 micro-refactor non-breaking."*

- Cita gli SSoT quando rilevante:
  - `docs/AGENTS_INDEX.md`,
  - `docs/PromptChain_spec.md`,
  - `docs/logging_events.md`,
  - `src/semantic/AGENTS.md`.

### 3.2 Prompt orientati al risultato (micro-PR)

- Chiedi sempre modifiche **piccole e idempotenti**:
  - *"Proponi una singola micro-PR per migliorare la leggibilità della funzione X senza cambiare il comportamento."*
  - *"Tocca solo questo file; se servono modifiche ad altri file, proponi uno step successivo, non farle in automatico."*

- Pretendi un diff chiaro:
  - *"Mostra il diff completo e spiegami a parole l’impatto di ogni blocco di cambiamento."*

### 3.3 Prompt con QA esplicita

- Integra sempre una richiesta di QA mirata:
  - *"Dopo la modifica esegui `pytest -q -k test_nome_relativo` e riportami l’esito."*
  - *"Se i test falliscono, prova una sola volta a correggere; se fallisce ancora, fermati e chiedi indicazioni."*

- Per task più grossi, agganciati al workflow standard:
  - *"Usa la pipeline QA standard del repo (ruff/black/typecheck/pytest mirati o `qa-safe` se disponibile)."*

### 3.4 Prompt per spiegazioni e revisione

- Chiedi sempre una spiegazione breve ma chiara:
  - *"Spiega perché questa soluzione è coerente con `.codex/CONSTITUTION.md` e con gli `AGENTS.md` dell’area."*
  - *"Indica cosa controlleresti in review, se fossi tu il Senior Reviewer."*

Queste tecniche funzionano sia in Prompt Chain che in uso diretto: la differenza è che nella Prompt Chain sono **strutturate**, mentre in uso diretto sei tu a costruirle ogni volta.

---

## 4. Workflow consigliato: Codex + Prompt Chain + Senior Reviewer

Un flusso “sano” e ripetibile può essere:

1. **Definisci l’obiettivo**
   - Cosa vuoi ottenere? Refactor? Nuova feature? Hardening di un servizio?
   - Quali file/servizi saranno coinvolti?

2. **Avvia la Prompt Chain tramite Onboarding**
   - Usa il Prompt 0 (Onboarding) per fissare contesto, regole e obiettivi.
   - Lascia che Codex faccia l’analisi iniziale (Prompt 1/2) e poi intervieni HiTL per confermare o correggere il piano.

3. **Lascia lavorare Codex a micro-PR**
   - Ogni step modifica poco, con QA intermedia.
   - Tu controlli gli step chiave, specialmente quando cambiano API o comportamento visibile.

4. **QA finale e riepilogo**
   - La Prompt Chain chiude con QA completa (`pre-commit` + `pytest -q`).
   - Codex produce un riepilogo delle modifiche: contesto, file coinvolti, coerenza con Constitution e AGENTS.

5. **Coinvolgi un Senior Reviewer quando serve**
   - Per refactor sensibili, nuove integrazioni (Drive, Vision, nuovi MCP server), cambi di architettura.
   - Codex prepara un messaggio di review che spiega cosa è stato fatto e perché.

---

## 5. Scenario: usare Codex in autonomia, in pratica

### 5.1 Chat: esplorazione e pianificazione

- Usa Chat quando vuoi:
  - chiarire una parte del codice,
  - disegnare un piano di refactor,
  - confrontare due possibili architetture.
- Qui puoi essere più libero, ma resta utile citare sempre file e servizi specifici.

### 5.2 Agent: esecuzione assistita

- Passa alla modalità Agent quando:
  - il piano è chiaro,
  - hai definito l’area di intervento,
  - vuoi che Codex scriva davvero codice, lanci QA, aggiorni documentazione.

- Ricorda sempre di chiedere:
  - micro-PR,
  - diff esplicito,
  - comandi eseguiti,
  - esito QA.

### 5.3 Full Access: casi eccezionali

- Usa Full Access solo quando:
  - devi fare migrazioni massive o operazioni ripetitive su tanti file,
  - lavori su branch separati,
  - sei consapevole dei rischi di rete e di comandi più "larghi".

---

## 6. Riferimenti rapidi

- **Prompt Chain**: definizione completa e contratto operativo → `docs/PromptChain_spec.md`.
- **Runbook Codex**: flussi operativi dettagliati → `docs/runbook_codex.md`.
- **Indice AGENTS**: vista centralizzata degli agenti → `docs/AGENTS_INDEX.md`.
- **Costituzione NeXT**: principi fondanti e regole di base → `.codex/CONSTITUTION.md`.
- **Coding Standards minimi**: → `.codex/CODING_STANDARDS.md`.
- **Configurazione personale**: → `~/.codex/AGENTS.md` e `~/.codex/config.toml`.

Questa guida è pensata per darti una mappa operativa chiara:
- Prompt Chain come percorso principale,
- uso diretto di Codex in VS Code quando serve più agilità,
- sempre con HiTL, Probabilismo e SSoT come linea guida di fondo.
