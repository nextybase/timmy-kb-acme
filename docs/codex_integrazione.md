# Integrazione di Codex in VS Code e sistema degli agenti

## Perché Codex in NeXT
Usiamo Codex come coding agent per accelerare sviluppo, refactoring e manutenzione guidata dai dati, mantenendo un approccio Human-in-the-Loop coerente con NeXT: iterazioni brevi, feedback continui e controllo di coerenza tra obiettivi e risultati. Questo si integra con i cicli NeXT (NeXT/Basket/Sprint) e con la Governance probabilistica, dove gli agenti forniscono insight e automazione, mentre il Team supervisiona e corregge rotta.

---

## Installazione e attivazione in VS Code
1. Installa l’estensione Codex dal Marketplace di VS Code.  
2. Aggiungi il pannello Codex nell’editor e scegli la modalità di approvazione:
   - **Agent (default):** può leggere file, proporre e applicare modifiche ed eseguire comandi nella working directory.
   - **Chat:** solo conversazione/pianificazione.
   - **Agent (Full Access):** include accesso rete e meno prompt di conferma — usare con cautela.

Puoi autenticarti con l’account ChatGPT (piani Plus/Pro/Team/Enterprise) oppure con API key.  
**Nota OS:** su Windows l’esperienza migliore è tramite WSL; l’estensione è pienamente supportata su macOS e Linux.

---

## Memoria di progetto: AGENTS.md
Codex supporta il file `AGENTS.md` per recepire regole, comandi e prassi del progetto. I file `AGENTS.md` fanno già parte integrante del repository: troverai la versione root e quelle nelle cartelle strategiche. Non c’è bisogno di crearli, ma solo di rispettarne le regole.

L’unico file che va aggiunto manualmente è quello **Personale**, nella home dello sviluppatore.

### Come creare il file Personale
Crea la cartella di configurazione locale (se non esiste già):
```bash
mkdir -p ~/.codex
```
Poi crea il file `~/.codex/AGENTS.md` e personalizzalo con preferenze e stile individuali. Esempio minimale:
```markdown
# AGENTS.md — Preferenze personali

## Stile
- Usa lingua ITA nelle risposte.
- Suggerisci sempre refactor idempotenti.

## Preferenze
- Mostra diff con evidenza.
- Prediligi micro‑PR.
```

Questo file non va versionato nel repo: resta locale al tuo ambiente.

---

## AGENTS.md per cartelle strategiche
- **docs/AGENTS.md:** regole per coerenza documentazione (lingua ITA, cSpell attivo, frontmatter e glossario, comandi `make docs`).
- **src/config_ui/AGENTS.md:** vincoli per componenti di interfaccia (es. `onboarding_ui.py`); build e test controllati, riscritture solo atomiche.
- **src/pipeline/AGENTS.md:** tutela dei flussi e delle orchestrazioni, regole sui prompt, nessuna modifica invasiva ai workflow.
- **src/semantic/AGENTS.md:** principio “DB first”: SQLite come SSoT per i tag; YAML ammesso solo in modalità legacy con nota di migrazione.
- **tests/AGENTS.md:** convenzioni per test (pytest), naming `test_*.py`, fixture leggere, niente I/O o rete nei unit test, uso di stub/fake, esiti deterministici, soglia minima di coverage.

Questi file, già presenti nel repo, assicurano che Codex lavori in coerenza con pipeline, architettura e vincoli di progetto.

---

## Configurazione avanzata (CLI + cartella ~/.codex/)
L’estensione si appoggia al Codex CLI open‑source. La configurazione avanzata vive in `~/.codex/` e supporta l’uso di MCP (Model Context Protocol) per collegare strumenti e fonti (filesystem, servizi, ecc.). Impostazioni tipiche: `~/.codex/config.toml`, `~/.codex/AGENTS.md`.

### Esempio minimo ~/.codex/config.toml
```toml
model = "gpt-5"
approval_mode = "agent"   # agent | chat | full

[mcp_servers.files]
type = "filesystem"
# Su Linux/macOS
root = "/home/<user>/workspace/timmy-kb-acme"
# Su Windows (PowerShell/WSL)
# root = "C:/Users/<User>/clienti/timmy-kb-acme"
```

MCP è un protocollo standard per esporre tool/contesto a un agente; in Codex si abilita dichiarando `mcp_servers` nella config. Architettura host–server e filtri tool sono documentati anche nell’Agents SDK di OpenAI.

Usa MCP per agganciare strumenti sicuri (es. solo filesystem del workspace). Per l’accesso al DB tag (SSoT) puoi valutare un server MCP specifico per SQLite, mantenendo il principio “DB first, YAML legacy”. (Allineamento richiesto anche nei relativi AGENTS.md di servizio.)

---

## Come si lavora con Codex nel repo
- **Scenario Chat:** brainstorming, piani di refactor, revisione architetturale (non scrive/non esegue).
- **Scenario Agent (consigliato):** esegue comandi locali, propone patch, rispetta le regole degli AGENTS.md, chiude il loop con test/lint.
- **Scenario Agent (Full Access):** usarlo solo per task espliciti ad alto sforzo (migrazioni massicce, rigenerazioni documentazione), su branch dedicati.

### Esempi di prompt efficaci
- “Allinea docs/ alle coding rules e ai termini glossario; applica correzioni cSpell e aggiorna frontmatter. Chiudi con make docs e allega diff.”
- “Nel servizio semantic.api, usa DB come SSoT per i tag; se trovi YAML trattalo come legacy. Scrivi migrazione e test.”
- “Rivedi onboarding_ui.py: spiega flusso, dipendenze e orchestratori chiamati; proponi 3 micro‑PR idempotenti con stima impatto.”

---

## Sicurezza, controllo e governance
Manteniamo **Agent** come default; **Full Access** solo su richiesta esplicita, branch isolati e PR obbligatoria. Gli AGENTS.md chiariscono comandi consentiti e verifiche (lint/test/build). Questo meccanismo rispetta il principio NeXT di controllo di coerenza continuo e di adattabilità alle condizioni di progetto/mercato.

---

## Coerenza con la filosofia del Probabilismo
Gli agenti sostengono decisioni e operatività con evidenze (test, metriche, KPI), mentre il team guida allineamento e correzioni. Così l’incertezza diventa leva: iteriamo, misuriamo, aggiorniamo regole negli AGENTS.md dove necessario, in linea con la Governance probabilistica.

---

## Riferimenti ufficiali e utili
- Documentazione estensione Codex IDE (installazione, modalità, cloud/offload).
- Codex CLI open‑source (configurazione `~/.codex`, MCP, AGENTS.md, sandbox e approvals).
- MCP con Agents SDK di OpenAI (attacco server, filtraggio tool).
- Che cos’è AGENTS.md (formato e priorità “file più vicino”).

