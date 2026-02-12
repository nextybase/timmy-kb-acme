# ADR-0006: Dummy KB as End-to-End Smoke Test
- Stato: Accepted
- Data: 2025-12-05
- Responsabili: Timmy KB Architecture Group; Franco Mennella; ChatGPT

## Contesto

Timmy KB richiede un meccanismo affidabile per verificare rapidamente:

- la salute dell'intera pipeline di onboarding (Vision → Semantic → RAW → Tags → Drive → Registry),
- la stabilità della UI e dei servizi backend,
- eventuali regressioni introdotte da refactor del codice,
- la correttezza del workflow end-to-end senza utilizzare dati reali.

Attualmente esiste lo strumento CLI
[`tools/gen_dummy_kb.py`](../../tools/gen_dummy_kb.py)
che genera una Knowledge Base "dummy", ma:

- non registra un cliente reale nel registry della UI,
- non esegue una validazione strutturale,
- non produce un report diagnostico armonizzato,
- non è ancora pensato come smoke test ufficiale del sistema.

La UI contiene già un pulsante dedicato alla generazione della Dummy KB in:
[`src/ui/chrome.py`](../../src/ui/chrome.py)
ma il suo comportamento attuale è limitato.

Per rafforzare la resilienza del sistema, si decide di trasformare la Dummy KB in un **E2E Smoke Test ufficiale**, cancellabile e rigenerabile con un singolo comando/azione.

Questo ADR è subordinato ad ADR-0007 (Dummy Manifesto), che governa il Dummy come "first-class architectural fixture"
e definisce i vincoli "same entrypoints as real clients", "smoke vs deep modes" e "health contract". Questo documento
descrive l'applicazione smoke/deep nel rispetto di tali vincoli, senza introdurre regole globali.

## Decisione

Viene adottata la seguente decisione architetturale:

> **La Dummy KB diventa un cliente reale, cancellabile e rigenerabile, usato ufficialmente come Smoke Test End-to-End dell'intero ecosistema Timmy KB.**

Questa applicazione è subordinata ad ADR-0007 e non modifica le regole di governance del Dummy.

La decisione si articola in sei punti:

1. **Registrazione Cliente Dummy**
   - Dopo la generazione del workspace, la dummy viene registrata nel registry UI tramite `upsert_client()` da
     [`src/ui/clients_store.py`](../../src/ui/clients_store.py).
   - La registrazione usa gli stessi entrypoints dei client reali ("same entrypoints as real clients").

2. **Rigenerabilità Completa**
   - La dummy viene progettata per essere cancellata e rigenerata senza lasciare residui.
   - La UI mantiene l'opzione "Cancella dummy (locale + Drive)" già presente in
     [`src/ui/chrome.py`](../../src/ui/chrome.py).
   - Nel rispetto dell'idempotenza del Manifesto, senza reset globali.

3. **Validazione strutturale (Smoke Test)**
   - Il tool esegue un insieme di verifiche obbligatorie su file e directory fondamentali:
     - `config/config.yaml`
     - `semantic/semantic_mapping.yaml`
     - `semantic/tags.db`
     - `book/README.md`
     - `book/SUMMARY.md`
     - almeno un PDF valido in `raw/`
   - In caso di assenza o inconsistenza → errore immediato.

4. **Health Report nel payload JSON**
   - Viene aggiunta una chiave `"health"` che riporta:
     - stato Vision,
     - uso degradazione compatibile smoke (semantica),
     - conteggio PDF raw,
     - validità mapping semantico,
     - presenza di SUMMARY.md,
     - conteggio README generati,
     - eventuali warning.
   - Il report health costituisce il "health contract" del Dummy.

5. **UI arricchita con Smoke Report**
  - La UI orchestra il flusso senza implementare di nuovo la logica e senza bypassare i contratti CLI/pipeline.
   - Il modal Dummy KB visualizza un pannello diagnostico basato sullo struct `"health"` ricevuto dal tool CLI.
   - Il template UI è definito in
     [`src/ui/chrome.py`](../../src/ui/chrome.py).

6. **Integrazione nei flussi di sviluppo e CI**
   - Viene introdotto un comando dedicato (`make dummy-smoke`) che invoca
     `python tools/gen_dummy_kb.py --slug dummy --reset`.
   - La generazione della dummy non avviene automaticamente all'avvio della UI, ma è uno strumento operativo a disposizione di sviluppatori e pipeline CI.

   - In CI si esegue solo smoke mode; il deep è manuale e diagnostico.

### Contratto deep testing

La modalità deep testing descrive lo stesso flusso controllato della Dummy KB smoke, ma con vincoli operativi più stringenti:
Questa sezione applica i "smoke vs deep modes" del Manifesto e non introduce regole globali.

- **Smoke** è l'esecuzione cablata: genera un workspace fittizio, valida la struttura e produce l'health report senza Vision/Drive reali quando disabilitati.
- **Deep** è la stessa pipeline con Vision e Drive attivi, senza degradazioni automatiche: ogni chiamata reale viene osservata, i controlli falliscono duramente (health.status="failed") e viene chiesto all'utente di riprovare solo quando i secrets/permessi sono adeguati.
- In deep non si ignora mai un errore Vision o Drive; una failure viene trasformata in `HardCheckError` e il payload health espone `errors`, `checks` ed `external_checks` con messaggi che collegano direttamente all'esito della Secrets Healthcheck UI.
- Il flag CLI `--deep-testing` (e la checkbox "Attiva testing profondo") attivano questa modalità e scrivono `health.mode="deep"` nel payload finale, insieme a un'entry `golden_pdf` con path, sha256 e dimensione (solo in deep).
- La selezione dei passi del Manifesto resta valida: passi disabilitati non eseguono e non modificano artefatti.

### Schema health (deep vs smoke)

| Campo | Descrizione | Presente in |
| --- | --- | --- |
| `mode` | `"smoke"` o `"deep"` | sempre |
| `status` | `"ok"` o `"failed"` | sempre |
| `errors` | liste di messaggi diagnostici | sempre |
| `checks` | elenco di controlli eseguiti (es. `"vision_hardcheck"`) | deep |
| `external_checks` | mappa `{check: {ok, details, latency_ms?}}` | deep |
| `golden_pdf` | `{path, sha256, bytes}` per il PDF generato | deep |

```json
{
  "mode": "smoke",
  "status": "ok",
  "vision_status": "ok",
  "readmes_count": 3,
  "errors": []
}
```

```json
{
  "mode": "deep",
  "status": "failed",
  "errors": [
    "Vision hard check failed; verifica secrets/permessi: ...",
    "Drive hard check fallito; verifica secrets/permessi/drive (...)"
  ],
  "checks": [
    "vision_hardcheck",
    "drive_hardcheck",
    "golden_pdf"
  ],
  "external_checks": {
    "vision_hardcheck": {
      "ok": false,
      "details": "Vision run failed | sentinel=..."
    },
    "drive_hardcheck": {
      "ok": false,
      "details": "Drive exception: ..."
    }
  },
  "golden_pdf": {
    "path": ".../raw/golden_dummy.pdf",
    "sha256": "abc123",
    "bytes": 1234
  }
}
```

Deep testing funge da segnale diagnostico: se fallisce, il messaggio riporta che i secrets/permessi non sono pronti e rimanda alla pagina Secrets Healthcheck. La modalità è "contract only": non introduce stati side effect e può essere ripetuta all'infinito.

### Motivazioni (Rationale)

#### Integrità del sistema
La pipeline Timmy KB è composta da numerosi componenti interdipendenti (Vision, YAML, semantic mapping, tags DB, Drive, registry).
La Dummy KB offre un contesto controllato per verificare l'intero flusso in pochi secondi.

#### Early Detection delle regressioni
La rigenerazione della Dummy KB intercetta rapidamente:
- errori introdotti da refactor,
- incompatibilità di configurazione,
- anomalie nel parsing YAML,
- comportamenti imprevisti della Vision pipeline.

#### Cliente reale ma isolato
La dummy viene registrata nel registry UI come cliente vero, rendendo testabili tutte le pagine:
- pannelli semantici,
- mapping,
- preview,
- tagging,
- gestione dei PDF.

#### Semplicità di integrazione
La UI possiede già un pulsante per generarla; l'estensione è naturale.
Il tool è già completo: necessita solo di modularizzazione, validazione e registrazione.

#### Rispetto del metodo NeXT
Questa scelta è coerente con:
- modello probabilistico (controllo continuo di anomalie),
- approccio Human-in-the-Loop (l'utente vede subito problemi),
- controllo dell'entropia (rigenerazione ripetuta che riporta il sistema allo stato base),
- design adattivo.

### Conseguenze

#### Positive
- Maggiore affidabilità e prevedibilità del sistema.
- Rilevamento precoce di regressioni strutturali.
- Possibilità di testing completo della UI su un cliente fittizio.
- Aumento della qualità dei rilasci (CI con smoke test automatico).
- Log molto più chiari e strutturati in caso di errore.

#### Negative / Trade-offs
- Aumento complessità del tool (mitigata da modularizzazione).
- Possibile confusione con clienti reali (mitigata con campo `dummy: true`).
- Necessità di manutenzione minima per mantenere aggiornato lo smoke test quando cambia la pipeline.

### Stato finale

Il refactor viene implementato nei seguenti file:

- CLI principale:
  [`tools/gen_dummy_kb.py`](../../tools/gen_dummy_kb.py)

- Nuovi moduli dummy (post-refactor):
 - tools/dummy/bootstrap.py
 - tools/dummy/semantic.py
 - tools/dummy/vision.py
 - tools/dummy/drive.py
 - tools/dummy/orchestrator.py


- UI (modal Dummy KB e toolbar):
[`src/ui/chrome.py`](../../src/ui/chrome.py)
[`src/ui/app_core/layout.py`](../../src/ui/app_core/layout.py)

- Registry clienti:
[`src/ui/clients_store.py`](../../src/ui/clients_store.py)

- Documentazione aggiornata:
- `docs/developer/developer_guide.md`
- `docs/streamlit_ui.md`
- `docs/adr/0006-dummy-kb-e2e-smoke-test.md`

### Riferimenti

- ADR-0007: Dummy Manifesto (SSoT).
- Strumento CLI originale:
[`tools/gen_dummy_kb.py`](../../tools/gen_dummy_kb.py)

- UI Dummy KB:
[`src/ui/chrome.py`](../../src/ui/chrome.py)

- Vision service:
[`src/ui/services/vision_provision.py`](../../src/ui/services/vision_provision.py)

- Drive runner:
[`src/ui/services/drive_runner.py`](../../src/ui/services/drive_runner.py)

- Tag storage:
[`src/storage/tags_store.py`](../../src/storage/tags_store.py)

- Documentazione di riferimento:
`docs/developer/developer_guide.md`,
`docs/developer/guida_codex.md`,
`docs/streamlit_ui.md`.

## Alternative considerate
Nessuna alternativa esplicitata nel testo originale.

## Revisione
Questo ADR resta subordinato ad ADR-0007.
