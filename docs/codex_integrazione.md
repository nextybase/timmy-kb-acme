# Integrazione di Codex in VS Code e sistema degli agenti (v1.0 Beta)

## Perche Codex in NeXT
Usiamo Codex come coding agent per accelerare sviluppo, refactoring e manutenzione guidata dai dati, mantenendo un approccio Human-in-theLoop coerente con NeXT: iterazioni brevi, feedback continui e controllo di coerenza tra obiettivi e risultati.

---

## Installazione e attivazione in VS Code
1. Installa l'estensione Codex dal Marketplace di VS Code.
2. Aggiungi il pannello Codex nell'editor e scegli la modalita di approvazione:
   - Agent (default): puo leggere file, proporre/applicare modifiche ed eseguire comandi nella working directory.
   - Chat: solo conversazione/pianificazione.
   - Agent (Full Access): include accesso rete e meno prompt di conferma  usare con cautela.

Accesso: via account ChatGPT (Plus/Pro/Team/Enterprise) oppure con API key.
Nota OS: su Windows l'esperienza migliore e tramite WSL; l'estensione e pienamente supportata su macOS e Linux.

---

## Approccio pratico all'uso di Codex (day-by-day)

**1) Modalita giusta per il task**  Usa *Agent* per refactor/manutenzione locale; *Chat* per brainstorming; *Full Access* solo per migrazioni massicce e su branch dedicati.
**2) Regole dove servono**  Framework AGENTS normalizzato: ogni file segue il template Scopo/Regole/Accettazione/Riferimenti; indice SSoT in `docs/AGENTS_INDEX.md` (ora con colonna "Task tipici dell'agente").
**3) Prompt minimi ma vincolanti**  Usa l'API mentale in `.codex/PROMPTS.md` (es. "Onboarding Task Codex") per entrypoint e richieste ripetibili; micro-PR idempotenti con diff esplicito e QA mirata.
**4) Coerenza automatica**  Se tocchi un `AGENTS.md`, rigenera la Matrice con `pre-commit run agents-matrix-check --all-files`; la CI ripete `python tools/gen_agents_matrix.py --check`.
**5) Sicurezza & qualita**  Path-safety/I-O atomico, niente side-effects a import-time; linting/typing e test deterministici **senza rete**.
**6) Performance**  Cache RAW PDF auto-invalidata da `safe_write_*` (config in `pipeline.raw_cache` di `config/config.yaml`); per NLP usa `--nlp-workers/--nlp-batch-size` e (se serve debug) `--nlp-no-parallel`.
**7) Explainability & lineage**  Ogni embedding porta un passaporto semantico in `meta["lineage"]` (source_id + chunk_id/embedding_id). Quando Codex tocca ingest o servizi semantic deve preservare/aggiornare il lineage e mantenere i log `semantic.input.received` / `semantic.lineage.chunk_created` / `semantic.lineage.embedding_registered` allineati a `docs/logging_events.md`.

Obiettivo: accelerare il lavoro senza sorprese. L'agente propone, tu approvi: HiTL come regola, *repo-aware* come prassi.

## Workflow Codex + Repo-Aware (v2)
- Lettura obbligatoria dei tre SSoT prima di ogni task: `docs/AGENTS_INDEX.md`, l'`AGENTS.md` dell'area e `~/.codex/AGENTS.md`.
- Entrypoint standard: prompt "Onboarding Task Codex" da `.codex/PROMPTS.md` (piano prima delle modifiche, micro-PR idempotenti, checklist QA).
- Collaborazione tripartita: Sviluppatore ↔ Codex ↔ Senior Reviewer; riepilogo e QA esplicita prima della review esterna.
- Principio micro-PR: patch piccole, atomiche, rilanciabili; se tocchi X aggiorna docs/test correlati.
- Pipeline QA standard: ruff, black, typecheck, pytest mirati (o target repo `qa-safe`) con esito riportato nel messaggio finale.
- Questo workflow e il percorso **predefinito** consigliato per qualsiasi attivita di sviluppo o refactor nel repo.

### Integrazione con `.codex/PROMPTS.md` (obbligatoria)
- I prompt in `.codex/PROMPTS.md` costituiscono la **API operativa** ufficiale per l’agente Codex.
- Prima di ogni task, Codex esegue il blocco “Task di avvio” indicato in PROMPTS.md (lettura AGENTS_INDEX, AGENTS area, `.codex/AGENTS.md`, runbook stesso).
- Il prompt **Onboarding Task Codex** è l’entrypoint vincolante per:
  - definire il piano di lavoro,
  - garantire micro-PR non-breaking,
  - applicare la checklist QA (path-safety, write atomiche, logging strutturato),
  - aggiornare documentazione e matrice AGENTS se toccate.
- Questo garantisce coerenza esatta con quanto definito in `.codex/PROMPTS.md`, che governa tutti i flussi di sviluppo assistito.

## Prompt Chain e OrchestratoreChainPrompt (OCP)
- **Prompt Chain**: sequenza numerata di prompt (Prompt 0, 1, 2, ...) eseguiti uno per volta, ciascuno con scope limitato e trattato come micro-PR secondo le regole Codex (HiTL, AGENT-first, QA, path-safety).
- **OrchestratoreChainPrompt (OCP)**: strato di orchestrazione sopra Codex; non modifica il repository, genera e inoltra i prompt della chain verso Codex. Ogni prompt viene eseguito singolarmente, senza batch.
- **Timmy/ProtoTimmy**: planner/logico che definisce gli obiettivi e passa sempre attraverso l'OCP per produrre prompt formali destinati a Codex.
- **Avvio**: la Prompt Chain parte solo su richiesta esplicita dell'utente; Codex non avvia catene autonomamente. L'entrypoint operativo resta "Onboarding Task Codex".

## Flusso Codex + Senior Reviewer
- Quando il task richiede review esterne (nuove feature, refactor sensibili, integrazioni Drive/Vision), Codex opera nel modello tripartito: sviluppatore umano (Franco/team), agente Codex e Senior Reviewer esterno.
- Prima di coinvolgere il Senior Codex prepara un riepilogo sintetico (contesto, file interessati, motivi di coerenza con `.codex/CONSTITUTION.md` e `docs/AGENTS_INDEX.md`) e usa i prompt dedicati in `.codex/PROMPTS.md` per la fase di coding e per il messaggio di review.
- Ogni modifica resta micro-PR idempotente, segue la pipeline QA locale (formatter, linter, type-checker, test) e documenta esplicitamente QA/dubbi/trade-off. La checklist in `.codex/CHECKLISTS.md` e il promemoria operativo.

---

## Prerequisiti Rapidi
- Installa l'estensione Codex in VS Code (oppure usa Codex CLI in locale).
- Crea la cartella di configurazione locale: `~/.codex/` (Windows: `C:\Users\<User>\.codex\`).
- Posiziona l'AGENTS personale in `~/.codex/AGENTS.md` (non versionato). Gli `AGENTS.md` di progetto restano nel repo.

Note di riferimento (link ufficiali):
- MCP  Specifica ufficiale: https://modelcontextprotocol.io  https://github.com/modelcontextprotocol/specification
- OpenAI Agents SDK (CLI/Agents): https://platform.openai.com/docs/agents  https://github.com/openai/agents

---

## Indice degli AGENT del progetto
- Indice centralizzato: `docs/AGENTS_INDEX.md` (policy comuni: build, test, lint, path-safety, doc update).
- Ogni `AGENTS.md` locale (root, docs/, src/pipeline/, src/semantic/, src/ui/, tests/) contiene solo override specifici e rimanda all'indice.
- Obiettivo: evitare duplicazioni e mantenere coerenza tra aree (regole comuni in un solo posto).

### Mantenere la Matrice AGENT aggiornata
Quando aggiorni un `AGENTS.md` (nuove **Regole** o **Accettazione**), rigenera la tabella in `docs/AGENTS_INDEX.md` eseguendo:

```bash
pre-commit run agents-matrix-check --all-files
```

Lo script riallinea automaticamente la matrice tra `<!-- MATRIX:BEGIN/END -->`.

> Nota: la pipeline CI esegue lo stesso controllo (`python tools/gen_agents_matrix.py --check`) nel job principale; se dimentichi di rigenerare la matrice, la build fallisce.

---

## Memoria di progetto e file personali
Codex legge i file `AGENTS.md` presenti nel repo e in `~/.codex/`. Il file personale non e versionato e definisce preferenze e stile individuali.

Esempio minimo `~/.codex/AGENTS.md`:
```markdown
# AGENTS.md  Preferenze personali

## Stile
- Usa lingua ITA nelle risposte.
- Suggerisci sempre refactor idempotenti.

## Preferenze
- Mostra diff con evidenza.
- Prediligi microPR.
```

---

## Configurazione avanzata (CLI + cartella ~/.codex/)
L'estensione si appoggia al Codex CLI open-source. La configurazione avanzata vive in `~/.codex/` e supporta l'uso di MCP (Model Context Protocol) per collegare strumenti e fonti (filesystem, servizi, ecc.). Impostazioni tipiche: `~/.codex/config.toml`, `~/.codex/AGENTS.md`.

Esempio `~/.codex/config.toml`:
```toml
# model = "override-locale"  # scommenta solo se vuoi forzare un modello diverso dal valore letto via get_vision_model()
approval_mode = "agent"   # agent | chat | full

[mcp_servers.files]
type = "filesystem"
# Linux/macOS
root = "/home/<user>/workspace/timmy-kb-acme"
# Windows
# root = "C:/Users/<User>/clienti/timmy-kb-acme"
# Il modello Vision resta quello definito in `config/config.yaml` e viene letto a runtime tramite `get_vision_model()`.
```

MCP e un protocollo standard per esporre tool/contesto a un agente; in Codex si abilita dichiarando `mcp_servers` nella config. Architettura host-server e filtri tool sono documentati anche nell'Agents SDK di OpenAI.

Usa MCP per agganciare strumenti sicuri (es. solo filesystem del workspace). Per l'accesso al DB tag (SSoT) puoi valutare un server MCP specifico per SQLite, mantenendo il principio "DB first, YAML solo bootstrap". (Allineamento richiesto anche nei relativi AGENTS.md di servizio.)

---

## Come si lavora con Codex nel repo
- Scenario Chat: brainstorming, piani di refactor, revisione architetturale (non scrive/non esegue).
- Scenario Agent (consigliato): esegue comandi locali, propone patch, rispetta l'indice `docs/AGENTS_INDEX.md` e gli `AGENTS.md` locali, chiude il loop con test/lint.
- Scenario Agent (Full Access): usarlo solo per task espliciti ad alto sforzo (migrazioni massicce, rigenerazioni documentazione), su branch dedicati.

## Pattern architetturali consigliati
- Collector + Orchestratore nei moduli UI: separa raccolta check (collector) e coordinamento (orchestratore), mantenendo ordine e output invariati (es. preflight UI).
- Refactor non-breaking: logica invariata, leggibilita aumentata, nessun cambio di firma o side-effect a import-time.
- Logging strutturato minimale, coerente con `docs/logging_events.md`: eventi sintetici, `extra` senza PII/segreti, solo per start/fail/complete.

Esempi di prompt efficaci
- "Applica Onboarding Task Codex su `src/ui/preflight.py`: identifica check e orchestrazione, proponi micro-refactor non-breaking (collector + orchestratore) e log strutturato minimale."
- "Allinea docs/ alle coding rules e ai termini glossario; applica correzioni cSpell e aggiorna frontmatter. Chiudi con make docs e allega diff."
- "Nel servizio semantic.api, usa DB come SSoT per i tag. Scrivi migrazione e test."
- "Rivedi onboarding_ui.py: spiega flusso, dipendenze e orchestratori chiamati; proponi 3 microPR idempotenti con stima impatto."

---

## Safety, QA e cSpell
- path-safety e I/O: qualsiasi write/copy/rm passa da util SSoT; niente side-effects a import-time.
- cSpell: configurato via `cspell.json` (EN/IT, dizionario italiano importato) e hook precommit locale su `README.md` e `docs/**/*.md`.
- Linters & Typecheck: Black, isort, Ruff; mypy/Pyright disponibili (pre-push: mypy e `qa-safe --with-tests`).

---

## Commit/Push: test preliminari eseguiti da Codex
Quando chiedi a Codex di preparare un commit/push, vengono lanciati i controlli predefiniti del repo:
- Precommit (su tutti i file toccati o `-a`):
  - check-yaml, end-of-file-fixer, trailing-whitespace, mixed-line-ending
  - Black, isort, Ruff (formattazione/lint)
- Hook locali: path-safety/emit-copy guards (tools/dev/*), gitleaks (secret scan)
  - cspell (README + docs)
- Pre-push (se richiesto o in CI):
  - mypy mirato (aree selezionate)
  - `qa-safe --with-tests` (linters/type + pytest se presente)

Nota: i target "safe" degradano in assenza degli strumenti (skip espliciti); gli errori bloccanti vengono riportati con indicazioni sul fix minimo.

---

## Riferimenti ufficiali e utili
- Documentazione estensione Codex IDE (installazione, modalita, cloud/offload).
- Codex CLI open-source (configurazione `~/.codex`, MCP, AGENTS.md, sandbox e approvals).
- MCP con Agents SDK di OpenAI (attacco server, filtraggio tool).
- Che cos'e AGENTS.md (formato e priorita "file piu vicino").
- [Runbook Codex](runbook_codex.md) - flussi operativi dettagliati per l'uso di Codex come agente.
