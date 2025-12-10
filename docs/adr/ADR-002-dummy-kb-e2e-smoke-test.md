---
adr: 002
title: "Dummy KB as End-to-End Smoke Test"
status: "Accepted"
date: 2025-12-05
authors:
  - "Timmy KB Architecture Group"
  - "Franco Mennella"
  - "ChatGPT"
---

# 1. Contesto

Timmy KB richiede un meccanismo affidabile per verificare rapidamente:

- la salute dell’intera pipeline di onboarding (Vision → Semantic → RAW → Tags → Drive → Registry),
- la stabilità della UI e dei servizi backend,
- eventuali regressioni introdotte da refactor del codice,
- la correttezza del workflow end-to-end senza utilizzare dati reali.

Attualmente esiste lo strumento CLI
[`src/tools/gen_dummy_kb.py`](../../src/tools/gen_dummy_kb.py)
che genera una Knowledge Base “dummy”, ma:

- non registra un cliente reale nel registry della UI,
- non esegue una validazione strutturale,
- non produce un report diagnostico armonizzato,
- non è ancora pensato come smoke test ufficiale del sistema.

La UI contiene già un pulsante dedicato alla generazione della Dummy KB in:
[`src/ui/chrome.py`](../../src/ui/chrome.py)
ma il suo comportamento attuale è limitato.

Per rafforzare la resilienza del sistema, si decide di trasformare la Dummy KB in un **E2E Smoke Test ufficiale**, cancellabile e rigenerabile con un singolo comando/azione.

---

# 2. Decisione

Viene adottata la seguente decisione architetturale:

> **La Dummy KB diventa un cliente reale, cancellabile e rigenerabile, usato ufficialmente come Smoke Test End-to-End dell’intero ecosistema Timmy KB.**

La decisione si articola in sei punti:

1. **Registrazione Cliente Dummy**
   - Dopo la generazione del workspace, la dummy viene registrata nel registry UI tramite `upsert_client()` da
     [`src/ui/clients_store.py`](../../src/ui/clients_store.py).

2. **Rigenerabilità Completa**
   - La dummy viene progettata per essere cancellata e rigenerata senza lasciare residui.
   - La UI mantiene l'opzione “Cancella dummy (locale + Drive)” già presente in
     [`src/ui/chrome.py`](../../src/ui/chrome.py).

3. **Validazione strutturale (Smoke Test)**
   - Il tool esegue un insieme di verifiche obbligatorie su file e directory fondamentali:
     - `config/config.yaml`
     - `semantic/semantic_mapping.yaml`
     - `semantic/cartelle_raw.yaml`
     - `semantic/tags.db`
     - `book/README.md`
     - `book/SUMMARY.md`
     - almeno un PDF valido in `raw/`
   - In caso di assenza o inconsistenza → errore immediato.

4. **Health Report nel payload JSON**
   - Viene aggiunta una chiave `"health"` che riporta:
     - stato Vision,
     - uso fallback semantico,
     - conteggio PDF raw,
     - validità mapping semantico,
     - presenza di SUMMARY.md,
     - conteggio README generati,
     - eventuali warning.

5. **UI arricchita con Smoke Report**
   - Il modal Dummy KB visualizza un pannello diagnostico basato sullo struct `"health"` ricevuto dal tool CLI.
   - Il template UI è definito in
     [`src/ui/chrome.py`](../../src/ui/chrome.py).

6. **Integrazione nei flussi di sviluppo e CI**
   - Viene introdotto un comando dedicato (`make dummy-smoke`) che invoca
     `python src/tools/gen_dummy_kb.py --slug dummy --reset`.
   - La generazione della dummy non avviene automaticamente all’avvio della UI, ma è uno strumento operativo a disposizione di sviluppatori e pipeline CI.

---

# 3. Motivazioni (Rationale)

### 3.1 Integrità del sistema
La pipeline Timmy KB è composta da numerosi componenti interdipendenti (Vision, YAML, semantic mapping, tags DB, Drive, registry).
La Dummy KB offre un contesto controllato per verificare l’intero flusso in pochi secondi.

### 3.2 Early Detection delle regressioni
La rigenerazione della Dummy KB intercetta rapidamente:
- errori introdotti da refactor,
- incompatibilità di configurazione,
- anomalie nel parsing YAML,
- comportamenti imprevisti della Vision pipeline.

### 3.3 Cliente reale ma isolato
La dummy viene registrata nel registry UI come cliente vero, rendendo testabili tutte le pagine:
- pannelli semantici,
- mapping,
- preview,
- tagging,
- gestione dei PDF.

### 3.4 Semplicità di integrazione
La UI possiede già un pulsante per generarla; l’estensione è naturale.
Il tool è già completo: necessita solo di modularizzazione, validazione e registrazione.

### 3.5 Rispetto del metodo NeXT
Questa scelta è coerente con:
- modello probabilistico (controllo continuo di anomalie),
- approccio Human-in-the-Loop (l’utente vede subito problemi),
- controllo dell’entropia (rigenerazione ripetuta che riporta il sistema allo stato base),
- design adattivo.

---

# 4. Conseguenze

### Positive
- Maggiore affidabilità e prevedibilità del sistema.
- Rilevamento precoce di regressioni strutturali.
- Possibilità di testing completo della UI su un cliente fittizio.
- Aumento della qualità dei rilasci (CI con smoke test automatico).
- Log molto più chiari e strutturati in caso di errore.

### Negative / Trade-offs
- Aumento complessità del tool (mitigata da modularizzazione).
- Possibile confusione con clienti reali (mitigata con campo `dummy: true`).
- Necessità di manutenzione minima per mantenere aggiornato lo smoke test quando cambia la pipeline.

---

# 5. Stato finale

Il refactor viene implementato nei seguenti file:

- CLI principale:
  [`src/tools/gen_dummy_kb.py`](../../src/tools/gen_dummy_kb.py)

- Nuovi moduli dummy (post-refactor):
 - src/tools/dummy/bootstrap.py
 - src/tools/dummy/semantic.py
 - src/tools/dummy/vision.py
 - src/tools/dummy/drive.py
 - src/tools/dummy/orchestrator.py


- UI (modal Dummy KB e toolbar):
[`src/ui/chrome.py`](../../src/ui/chrome.py)
[`src/ui/app_core/layout.py`](../../src/ui/app_core/layout.py)

- Registry clienti:
[`src/ui/clients_store.py`](../../src/ui/clients_store.py)

- Documentazione aggiornata:
- `docs/developer_guide.md`
- `docs/streamlit_ui.md`
- `docs/adr/ADR-002-dummy-kb-e2e-smoke-test.md`

---

# 6. Riferimenti

- Strumento CLI originale:
[`src/tools/gen_dummy_kb.py`](../../src/tools/gen_dummy_kb.py)

- UI Dummy KB:
[`src/ui/chrome.py`](../../src/ui/chrome.py)

- Vision service:
[`src/ui/services/vision_provision.py`](../../src/ui/services/vision_provision.py)

- Drive runner:
[`src/ui/services/drive_runner.py`](../../src/ui/services/drive_runner.py)

- Tag storage:
[`src/storage/tags_store.py`](../../src/storage/tags_store.py)

- Documentazione di riferimento:
`docs/developer_guide.md`,
`docs/guida_codex.md`,
`docs/streamlit_ui.md`.

---
