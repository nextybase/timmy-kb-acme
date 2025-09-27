# Integrazione di Codex in VS Code e sistema degli agenti (v1.9.6)

## Perché Codex in NeXT
Usiamo Codex come coding agent per accelerare sviluppo, refactoring e manutenzione guidata dai dati, mantenendo un approccio Human‑in‑the‑Loop coerente con NeXT: iterazioni brevi, feedback continui e controllo di coerenza tra obiettivi e risultati.

---

## Installazione e attivazione in VS Code
1. Installa l’estensione Codex dal Marketplace di VS Code.
2. Aggiungi il pannello Codex nell’editor e scegli la modalità di approvazione:
   - Agent (default): può leggere file, proporre/applicare modifiche ed eseguire comandi nella working directory.
   - Chat: solo conversazione/pianificazione.
   - Agent (Full Access): include accesso rete e meno prompt di conferma — usare con cautela.

Accesso: via account ChatGPT (Plus/Pro/Team/Enterprise) oppure con API key.
Nota OS: su Windows l’esperienza migliore è tramite WSL; l’estensione è pienamente supportata su macOS e Linux.

---

## Prerequisiti Rapidi
- Installa l’estensione Codex in VS Code (oppure usa Codex CLI in locale).
- Crea la cartella di configurazione locale: `~/.codex/` (Windows: `C:\Users\<User>\.codex\`).
- Posiziona l’AGENTS personale in `~/.codex/AGENTS.md` (non versionato). Gli `AGENTS.md` di progetto restano nel repo.

Note di riferimento (link ufficiali):
- MCP — Specifica ufficiale: https://modelcontextprotocol.io • https://github.com/modelcontextprotocol/specification
- OpenAI Agents SDK (CLI/Agents): https://platform.openai.com/docs/agents • https://github.com/openai/agents

---

## Indice degli AGENT del progetto
- Indice centralizzato: `docs/AGENTS_INDEX.md` (policy comuni: build, test, lint, path‑safety, doc update).
- Ogni `AGENTS.md` locale (root, docs/, src/pipeline/, src/semantic/, src/ui/, tests/) contiene solo override specifici e rimanda all’indice.
- Obiettivo: evitare duplicazioni e mantenere coerenza tra aree (regole comuni in un solo posto).

---

## Memoria di progetto e file personali
Codex legge i file `AGENTS.md` presenti nel repo e in `~/.codex/`. Il file personale non è versionato e definisce preferenze e stile individuali.

Esempio minimo `~/.codex/AGENTS.md`:
```markdown
# AGENTS.md — Preferenze personali

## Stile
- Usa lingua ITA nelle risposte.
- Suggerisci sempre refactor idempotenti.

## Preferenze
- Mostra diff con evidenza.
- Prediligi micro‑PR.
```

---

## Configurazione avanzata (CLI + cartella ~/.codex/)
L’estensione si appoggia al Codex CLI open‑source. La configurazione avanzata vive in `~/.codex/` e supporta l’uso di MCP (Model Context Protocol) per collegare strumenti e fonti (filesystem, servizi, ecc.). Impostazioni tipiche: `~/.codex/config.toml`, `~/.codex/AGENTS.md`.

Esempio `~/.codex/config.toml`:
```toml
model = "gpt-5"
approval_mode = "agent"   # agent | chat | full

[mcp_servers.files]
type = "filesystem"
# Linux/macOS
root = "/home/<user>/workspace/timmy-kb-acme"
# Windows
# root = "C:/Users/<User>/clienti/timmy-kb-acme"
```

MCP è un protocollo standard per esporre tool/contesto a un agente; in Codex si abilita dichiarando `mcp_servers` nella config. Architettura host–server e filtri tool sono documentati anche nell’Agents SDK di OpenAI.

Usa MCP per agganciare strumenti sicuri (es. solo filesystem del workspace). Per l’accesso al DB tag (SSoT) puoi valutare un server MCP specifico per SQLite, mantenendo il principio “DB first, YAML legacy”. (Allineamento richiesto anche nei relativi AGENTS.md di servizio.)

---

## Come si lavora con Codex nel repo
- Scenario Chat: brainstorming, piani di refactor, revisione architetturale (non scrive/non esegue).
- Scenario Agent (consigliato): esegue comandi locali, propone patch, rispetta l’indice `docs/AGENTS_INDEX.md` e gli `AGENTS.md` locali, chiude il loop con test/lint.
- Scenario Agent (Full Access): usarlo solo per task espliciti ad alto sforzo (migrazioni massicce, rigenerazioni documentazione), su branch dedicati.

Esempi di prompt efficaci
- “Allinea docs/ alle coding rules e ai termini glossario; applica correzioni cSpell e aggiorna frontmatter. Chiudi con make docs e allega diff.”
- “Nel servizio semantic.api, usa DB come SSoT per i tag; se trovi YAML trattalo come legacy. Scrivi migrazione e test.”
- “Rivedi onboarding_ui.py: spiega flusso, dipendenze e orchestratori chiamati; proponi 3 micro‑PR idempotenti con stima impatto.”

---

## Safety, QA e cSpell
- Path‑safety e I/O: qualsiasi write/copy/rm passa da util SSoT; niente side‑effects a import‑time.
- cSpell: configurato via `cspell.json` (EN/IT, dizionario italiano importato) e hook pre‑commit locale su `README.md` e `docs/**/*.md`.
- Linters & Type‑check: Black, isort, Ruff; mypy/Pyright disponibili (pre‑push: mypy e `qa-safe --with-tests`).

---

## Commit/Push: test preliminari eseguiti da Codex
Quando chiedi a Codex di preparare un commit/push, vengono lanciati i controlli predefiniti del repo:
- Pre‑commit (su tutti i file toccati o `-a`):
  - check‑yaml, end‑of‑file‑fixer, trailing‑whitespace, mixed‑line‑ending
  - Black, isort, Ruff (formattazione/lint)
  - Hook locali: path‑safety/emit‑copy guards (tools/dev/*), gitleaks (secret scan)
  - cspell (README + docs)
- Pre‑push (se richiesto o in CI):
  - mypy mirato (aree selezionate)
  - `qa-safe --with-tests` (linters/type + pytest se presente)

Nota: i target “safe” degradano in assenza degli strumenti (skip espliciti); gli errori bloccanti vengono riportati con indicazioni sul fix minimo.

---

## Riferimenti ufficiali e utili
- Documentazione estensione Codex IDE (installazione, modalità, cloud/offload).
- Codex CLI open‑source (configurazione `~/.codex`, MCP, AGENTS.md, sandbox e approvals).
- MCP con Agents SDK di OpenAI (attacco server, filtraggio tool).
- Che cos’è AGENTS.md (formato e priorità “file più vicino”).
