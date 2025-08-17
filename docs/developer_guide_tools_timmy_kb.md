# Developer Guide – Tools

Questa sezione descrive i tool interattivi disponibili in `src/tools/`, il loro scopo e come usarli correttamente durante lo sviluppo.

> **Principi comuni**
>
> - **Interattivi, standalone**: i tool non sono pensati per essere richiamati dagli orchestratori; si usano da terminale.
> - **Logging strutturato**: output principale via logger; i “non-eventi” (es. path assenti) stanno a **DEBUG**.
> - **Bootstrap import**: ogni script inizializza il `PYTHONPATH` per permettere gli import da `pipeline.*` quando lanciato da `src/tools`.
> - **Sicurezza**: operazioni distruttive con richiesta esplicita dell’utente (conferma), path-safety dove rilevante, e **backup `.bak`** per sostituzioni.
> - **Compatibilità**: nessun `sys.exit()` nel corpo modulo; la CLI chiude con codici di ritorno dal `main()`.

---

## 1) `cleanup_repo.py`
**Scopo**: rimuovere in modo sicuro gli artefatti locali di uno **slug** cliente e, opzionalmente, eliminare il repository remoto GitHub convenzionale.

**Cosa elimina (locale)**
- `output/timmy-kb-<slug>`
- `clienti/<slug>`
- opzionale: `_book`, `book.json`, `package.json`

**Opzionale (remoto)**
- `gh repo delete <org|user>/timmy-kb-<slug>` (richiede GitHub CLI e permessi)

**Flusso (interattivo)**
1. Prompt **slug** → validazione (minuscole/numeri/trattini).
2. Prompt: includere artefatti globali? (NO di default)
3. Prompt: eliminare anche il repo remoto? (NO di default) → se SÌ, chiedi **namespace** (org o user).
4. Riepilogo e **conferma finale**.
5. Esecuzione, con log INFO per le rimozioni e DEBUG per i path non presenti.

**Note & gotcha**
- Su Windows, eventuali file lock possono impedire la rimozione: chiudi processi/Editor puntati nelle cartelle target.
- Se `gh` non è installato o non autorizzato, la cancellazione remota viene saltata con warning.

---

## 2) `gen_dummy_kb.py`
**Scopo**: generare una Knowledge Base di **test** standardizzata per verificare la pipeline end-to-end.

**Caratteristiche**
- **Slug fisso**: `dummy` (nessun prompt per lo slug).
- Genera struttura `output/timmy-kb-dummy/`:
  - `book/` con `README.md`, `SUMMARY.md`, `test.md`
  - `config/` con `config.yaml` minimo (drive/repo/branch/token caricati da env se presenti)
  - `raw/` organizzata in cartelle secondo **`config/cartelle_raw.yaml`**
- Genera **PDF di esempio** per ogni cartella RAW secondo **`config/pdf_dummy.yaml`**
  - Se la libreria `fpdf` non è disponibile → crea `.txt` placeholder (fallback non bloccante)
- Prompt **opzionale**: crea la cartella `output/timmy-kb-dummy/repo` per test GitHub.

**Flusso (interattivo)**
1. Crea cartelle base e file minimi in `book/`.
2. Legge gli YAML di configurazione e genera RAW + PDF dummy.
3. Chiede se creare la cartella `repo/` di test (default NO).

**Note & gotcha**
- Gli ID Drive “dummy” nel `config.yaml` sono segnaposto utili per test locali; non garantiscono accesso reale.
- Il fallback `.txt` permette di testare la pipeline anche senza dipendenze extra.

---

## 3) `refactor_tool.py`
**Scopo**: utility di manutenzione del codice/documenti con due modalità separate.

**Modalità**
1. **Trova (solo ricerca)**
   - Input: stringa da trovare (supporto **regex** opzionale)
   - Output: elenco file coinvolti e conteggio occorrenze, nessuna modifica ai file
2. **Trova & Sostituisci**
   - Input: stringa/regex da trovare, stringa di sostituzione, scelta **dry-run**
   - Anteprima: conteggi per file + (in dry-run) diff semplificato riga/riga
   - Applicazione: **backup `.bak`** e scrittura modifiche

**Flusso (interattivo)**
1. Menu principale: `Trova`, `Trova & Sostituisci`, `Esci`.
2. Richiesta cartella radice (default: root progetto), filtri estensioni/dir esclusi coerenti con il repo.
3. Esecuzione con log INFO per le modifiche e DEBUG per skip/letture fallite.

**Note & gotcha**
- In **dry-run** non si scrive nulla: usare per una prima valutazione impatto.
- Evitare regex troppo generiche: possono espandersi su grandi porzioni di file; testare prima in dry-run.

---

## Standard di logging
- **INFO**: operazioni eseguite (rimozioni applicate, sostituzioni effettuate, PDF generati).
- **WARNING**: condizioni non bloccanti ma rilevanti (es. `gh` non trovato, errori di scrittura su un file specifico).
- **DEBUG**: “non-eventi” e diagnostica (path assente/skip, errori di lettura non critici), disabilitabili in produzione.

---

## Troubleshooting rapido
- **Permission denied / file lock**: su Windows chiudere editor/processi che tengono file/cartelle aperti.
- **Nothing to do**: è normale vedere log DEBUG di path assenti se alcune cartelle non sono state ancora create.
- **gh delete fallisce**: verificare installazione/`gh auth status` e permessi sul namespace.

---


