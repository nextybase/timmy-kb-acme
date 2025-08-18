# Documentazione Timmy-KB – Versione 1.0.4 (Stable)

Benvenuto nella documentazione ufficiale di **Timmy-KB**, organizzata per fornire una panoramica chiara e navigabile delle funzionalità, dell’architettura e delle regole di sviluppo del progetto.

---

## 📚 Indice dei documenti

### 1. Architettura e Struttura Tecnica
- [Architettura tecnica](architecture.md) → Panoramica del sistema, flusso degli orchestratori, funzioni chiave e fonti dati.

### 2. Sviluppo e Standard
- [Guida sviluppatore](developer_guide.md) → Struttura del repository, principi architetturali, flussi di lavoro.
- [Regole di codifica](coding_rule.md) → Convenzioni, standard di scrittura del codice, sicurezza e principi NeXT.

### 3. Utilizzo e Operatività
- [Guida utente](user_guide.md) → Installazione, esecuzione pipeline (pre-onboarding e onboarding full), output e troubleshooting.

### 4. Policy e Governance Documentale
- [Policy di push](policy_push.md) → Quando pubblicare, quando usare `--no-push`, uso consapevole di `--force` e coerenza con `GIT_DEFAULT_BRANCH`.
- [Versioning](versioning_policy.md) → Regole di SemVer leggero, tag di rilascio e aggiornamento contestuale del CHANGELOG.

---

## 🔍 Come usare questa documentazione
1. **Per iniziare** → Leggi la [Guida utente](user_guide.md) per capire come installare e avviare Timmy-KB.
2. **Per contribuire** → Consulta la [Guida sviluppatore](developer_guide.md) e le [Regole di codifica](coding_rule.md) prima di aprire una Pull Request.
3. **Per comprendere il funzionamento interno** → Approfondisci l’[Architettura tecnica](architecture.md).
4. **Per pubblicare correttamente** → Verifica [Policy di push](policy_push.md) e [Versioning](versioning_policy.md).

---

## 📅 Versione attuale
- **Versione**: 1.0.4 Stable  
- **Data rilascio**: 18 Agosto 2025  
- **Stato**: Documentazione aggiornata e allineata al CHANGELOG 1.0.4.

### Note su questa versione
- **Logging strutturato unico**: un solo file per cliente con supporto opzionale a rotazione e degradazione sicura a console-only.  
- **Drive utils patchati**: BFS ricorsivo, retry con tetto temporale, idempotenza MD5/size e redazione log opzionale.  
- **Preview Docker migliorata**: auto-skip in non-interattivo, prompt in interattivo; supporto redazione log.  
- **Slug CLI “soft”**: supporto allo slug posizionale e a `--slug`; in interattivo, se assente, viene richiesto a prompt.  
- **Release di consolidamento**: nessun cambio di flusso, retro-compatibile con 1.0.3.  

---

## 📌 Note finali
- Tutti i file `.md` nella cartella `docs/` sono mantenuti aggiornati in parallelo all’evoluzione del codice.
- Le modifiche al codice che impattano la documentazione devono essere accompagnate da un aggiornamento coerente dei file.
