# Onboarding UI — guida aggiornata

Questa guida descrive **come usare e come funziona** l’interfaccia `onboarding_ui.py`, il suo inserimento nella pipeline, le dipendenze e i casi d’errore più comuni. È pensata per sostituire/aggiornare `docs/guida_ui.md`.

> In sintesi: la UI è una app **Streamlit** con tre step operativi — **Configurazione**, **Drive**, **Semantica** — e opzionale **Preview Docker (HonKit)**. Alcune funzioni degradano con *fallback* se i moduli di pipeline non sono disponibili.

---

## 1) Prerequisiti

**Obbligatori**

- Python 3.10+ e **Streamlit** installato
- Repository clonato e avviato dalla *root*

**Per la tab “Drive”**

- Credenziali Google Drive configurate (es. `SERVICE_ACCOUNT_FILE`)
- ID dell’unità o cartella di lavoro (es. `DRIVE_ID`)

**Per la Preview**

- **Docker** installato e in esecuzione
- Porta TCP libera (configurabile in UI)

**Logging/Redazione (opzionale ma consigliato)**

- Variabili: `LOG_REDACTION` / `LOG_REDACTED` (attiva redazione log) e/o `ENV=prod`

---

## 2) Avvio

Da root del repo:

- macOS/Linux: `streamlit run onboarding_ui.py`
- Windows: `streamlit run onboarding_ui.py`

La **landing** chiede `slug` e `nome cliente`. Quando entrambi sono valorizzati, la UI si “sblocca” e salva lo stato in sessione. C’è un pulsante “Chiudi UI” per terminare il processo Streamlit in modo pulito.

---

## 3) Struttura logica e stato

La UI usa `st.session_state` per:

- **Lock cliente**: blocca `slug`/`nome` dopo l’inserimento
- **Stato Drive**: progress provisioning e download
- **Gate Semantica**: la tab **Semantica** appare **solo dopo** il download locale dei PDF su `raw/`
- **Preview**: nome container, porta e stato *running*/*stopped*

La redazione log è calcolata con una funzione “safe” che preferisce la logica di pipeline se disponibile; in assenza, abilita la redazione se `ENV=prod` o se trovate variabili esplicite.

---

## 4) Tab “Configurazione”

Scopo: definire/raffinare il **mapping semantico** del cliente (categorie, descrizioni, esempi, alias/tag suggeriti).

**Cosa fa**

- Carica il mapping **rivisto** se presente; altrimenti carica un **default**
- Mostra editor per **una categoria alla volta** (comodo per iterazioni HiTL)
- Valida le categorie (duplicati, campi obbligatori, coerenza)
- Opzione di **normalizzazione chiavi** (kebab-case) per coerenza
- Salvataggio **puntuale** (della categoria) o **integrale** (tutto il mapping)

**Funzioni usate (modulo **``**)**

- `load_default_mapping()` / `load_tags_reviewed()`
- `split_mapping(mapping)` → parti editabili vs. riservate
- `validate_categories(cats)`
- `build_mapping(cats, reserved)` → ricompone la struttura
- `save_tags_reviewed(mapping)`

**File & percorsi**

- Il mapping rivisto viene salvato in `semantic/tags_reviewed.yaml` **nel workspace del cliente** (vedi §7)
- Le utilità interne adottano scritture atomiche e *path-safety*

> Nota: la sezione `context` (se esiste nel mapping) non è esposta in UI.

---

## 5) Tab “Drive”

Scopo: **provisioning** della struttura su Google Drive a partire dal mapping, **README** nelle sottocartelle di `raw/` e **download** dei contenuti localmente.

**Sequenza tipica**

1. **Crea/aggiorna struttura**: genera l’albero cartelle per il cliente, incluse `raw/` e sotto-cartelle per ambiti/categorie
2. **Genera README per \*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\***``: PDF (o TXT fallback) caricati su Drive, uno per sottocartella, per istruire l’upload dei materiali
3. **Download contenuti**: scarica i file da Drive su disco locale → `raw/` del workspace; al termine imposta lo stato `raw_downloaded=True`

**Funzioni usate (modulo **``**)**

- `build_drive_from_mapping(slug, client_name, progress_cb)`
- `emit_readmes_for_raw(slug)`
- `download_raw_from_drive_with_progress(slug)` (se disponibile) o `download_raw_from_drive(slug)`

**Requisiti ENV**

- `SERVICE_ACCOUNT_FILE` → credenziali Service Account
- `DRIVE_ID` → id dello *space*/cartella di lavoro

**Output locale**

- Workspace cliente: `output/timmy-kb-<slug>/`
  - `raw/` → PDF scaricati (naming sicuro)
  - altri metadati di provisioning

> La tab **Semantica** resta nascosta finché non viene completato almeno un download su `raw/`.

---

## 6) Tab “Semantica”

Scopo: conversione **RAW → BOOK** (PDF→Markdown), **arricchimento frontmatter** con tag canonici e generazione/validazione di **README & SUMMARY** per la navigazione; opzionalmente **Preview Docker**.

**Context**

- La tab crea un `ClientContext` puntato al workspace locale del cliente
- Non richiede variabili ENV esterne (si lavora su disco)

**Step operativi**

1. **Converti PDF in Markdown**

   - Converte i contenuti di `raw/` in `book/` (una dir di Markdown puliti)
   - Se l’utility di conversione non è disponibile, esce con avviso senza distruggere lo stato

2. **Arricchisci frontmatter**

   - Carica il **vocabolario rivisto** (SSoT attuale: **DB SQLite** gestito da `storage/tags_store`, migrato dallo YAML storico)
   - Aggiunge frontmatter coerente (`title`, `tags` canonici, eventuali alias)

3. **README & SUMMARY**

   - Genera/aggiorna i file di navigazione del libro (compatibili con HonKit/GitBook)
   - Se le utilità “ufficiali” non sono disponibili, usa *fallback* **idempotenti** per garantire la presenza minima dei file

4. **Preview Docker (HonKit)**

   - Avvia **container** con nome sicuro (default: `gitbook-<slug>`) e porta configurabile
   - Stato del container tracciato in sessione; pulsanti **Start/Stop**
   - Messaggi guida se Docker non è attivo o la porta è occupata

**Funzioni usate**

- Modulo `semantic_api` (API operative):
  - `_convert_raw_to_book(context)`
  - `_enrich_frontmatter(context, vocab)`
  - `_write_summary_and_readme(context)`
  - `_load_reviewed_vocab(context)`
- Modulo `adapters.preview` (preview Docker):
  - `start_preview(context, port, container_name)`
  - `stop_preview(context, container_name)`

**Output locale**

- `output/timmy-kb-<slug>/`
  - `raw/` → input scaricati da Drive
  - `book/` → Markdown convertiti
  - `README.md`, `SUMMARY.md` nella radice del libro

---

## 7) Workspace del cliente (layout)

Per ogni `slug` la UI lavora in un **workspace locale** sotto `output/`:

```
output/
  timmy-kb-<slug>/
    raw/            # PDF e fonti originali scaricate
    book/           # Markdown generati
    semantic/
      tags_reviewed.yaml   # mapping rivisto (origine storica)
      … (eventuale DB SQLite per i tag “reviewed”, gestito da storage/tags_store)
    README.md
    SUMMARY.md
```

> Nota importante: **SSoT dei tag “reviewed”**. L’interfaccia continua a salvare/mantenere lo YAML `semantic/tags_reviewed.yaml`, ma le funzioni semantiche leggono i tag consolidati da un **DB SQLite** (migrato dallo YAML) per garantire audit e versioning. Se il DB non è presente, viene rigenerato/aggiornato a partire dallo YAML quando previsto dal codice.

---

## 8) Logging & redazione

- La UI tenta di usare un **logger strutturato** della pipeline; in fallback usa `logging.basicConfig`
- Il flag di **redazione** (mascheramento dati sensibili nei log) è calcolato così:
  1. Se disponibile, usa la funzione di pipeline (`compute_redact_flag`)
  2. In alternativa, abilita se `LOG_REDACTION`/`LOG_REDACTED` è truthy o se `ENV=prod`

---

## 9) Errori comuni & soluzioni

**Docker non attivo / porta occupata**

- Avvia Docker Desktop; scegli una porta libera; riprova `Start Preview`

**Credenziali Drive mancanti**

- Verifica `SERVICE_ACCOUNT_FILE` e `DRIVE_ID`; riesegui la tab Drive

**RAW vuota o conversione fallita**

- Assicurati che il download abbia popolato `raw/` e che i PDF siano leggibili
- Riprova “Converti PDF in Markdown”; controlla il log per filename problematici

**Validazione mapping**

- Correggi duplicati, rinomina con normalizzazione chiavi (opzione dedicata), salva e riprova

**Container “bloccato”**

- Usa `Stop Preview`; se serve, elimina manualmente il container `gitbook-<slug>` e riavvia

---

## 10) Best practice operative

- Procedi **in ordine**: Configurazione → Drive → Semantica → Preview
- Mantieni il mapping “rivisto” **coerente** con i materiali effettivi in `raw/`
- Usa la **normalizzazione chiavi** per tag/categorie stabili e prevedibili
- Evita spazi/caratteri speciali nei nomi file sorgenti
- Tieni Docker avviato **solo** quando serve la preview

---

## 11) API surface (per sviluppatori)

``

- `load_default_mapping()` / `load_tags_reviewed()`
- `split_mapping(mapping)`
- `validate_categories(cats)`
- `build_mapping(cats, reserved)`
- `save_tags_reviewed(mapping)`

``

- `build_drive_from_mapping(slug, client_name, progress_cb=None)`
- `emit_readmes_for_raw(slug)`
- `download_raw_from_drive_with_progress(slug)` → preferita se disponibile
- `download_raw_from_drive(slug)` → fallback

``

- `_load_reviewed_vocab(context)`
- `_convert_raw_to_book(context)`
- `_enrich_frontmatter(context, vocab)`
- `_write_summary_and_readme(context)`

``

- `start_preview(context, port, container_name='gitbook-<slug>')`
- `stop_preview(context, container_name)`

---

---

## 12) FAQ

**Posso usare la tab Semantica senza Drive?**\
Sì, se hai già i PDF in `raw/` locale.

**Posso fermare la UI in sicurezza?**\
Sì, con il pulsante “Chiudi UI” o interrompendo Streamlit dal terminale.

**Dove trovo i file generati?**\
In `output/timmy-kb-<slug>/book/` e nella radice del workspace (`README.md`, `SUMMARY.md`).

---

## 13) Appendice: comandi utili

- Avvio UI: `streamlit run onboarding_ui.py`
- Alternative Windows: `streamlit run onboarding_ui.py`
- (Debug) Avvio preview manuale: usa i bottoni in UI; evita di eseguire docker a mano a meno di necessità

---

> **Versione**: 2025-09-01\
> **Stato**: Allineata all’implementazione corrente di `onboarding_ui.py` e ai moduli correlati. Per modifiche, aprire PR su `docs/guida_ui.md`.
\n+## Novità: API semantica pubblica (facade)

- Da ora la UI può importare funzioni stabili da `semantic.api` invece di usare helper privati con underscore da `semantic_onboarding`.
- Obiettivo: stabilizzare l’API per la UI, mantenendo liberi gli internals di evolvere senza breaking changes.

Funzioni esposte in `semantic.api`:
- `get_paths(slug)`: percorsi `base/raw/book/semantic` per lo slug.
- `load_reviewed_vocab(base_dir, logger)`: carica il vocabolario canonico (da `semantic/tags_reviewed.yaml`).
- `convert_markdown(context, logger, *, slug)`: converte PDF in Markdown sotto `book/`.
- `enrich_frontmatter(context, logger, vocab, *, slug)`: arricchisce frontmatter (`title`, `tags`).
- `write_summary_and_readme(context, logger, *, slug)`: genera/valida `SUMMARY.md` e `README.md`.

Esempio di import consigliato per la UI:

```python
from semantic.api import (
    get_paths,
    load_reviewed_vocab,
    convert_markdown,
    enrich_frontmatter,
    write_summary_and_readme,
)
```

Note di transizione:
- Gli import esistenti da `semantic_onboarding` continuano a funzionare per compatibilità, ma si consiglia di migrare alla facade.
- Le firme pubbliche riportate qui sono considerate stabili; eventuali cambiamenti saranno versionati e documentati.
\n+## Prerequisiti
- Docker attivo (Docker Desktop su Windows/macOS; WSL2 su Windows consigliato).
- Porte libere per la preview (default `4000`). Configurabile dalla UI.
- Ambiente Drive opzionale: credenziali e permessi se si usa il download da Drive.
- Python 3.10+ e dipendenze installate secondo `requirements*.txt`.

Checklist rapida
- `docker info` deve rispondere senza errori.
- Verifica porta: apri `http://127.0.0.1:4000` dopo l’avvio preview.
- Se usi Drive: test del token/credenziali con il comando di download.

## SSoT Tag e Migrazione (YAML → SQLite)
- Fonte di verità dei tag: `output/<slug>/semantic/tags.db` (SQLite).
- Il vecchio `tags_reviewed.yaml` resta supportato come input per migrare.
- Script di migrazione: `tools/migrate_yaml_to_db.py`.
  - Converte il contenuto YAML in schema `v2` su SQLite in modo idempotente.
  - Esegue l’upsert di meta, tag e sinonimi.
- Runtime: l’orchestratore e la UI leggono dallo SQLite per coerenza e prestazioni.

Suggerimenti operativi
- Tieni versionato il YAML e genera lo SQLite durante il run (build artifact locale).
- Usa la UI per validare dopo migrazione (frontmatter enrichment + README/SUMMARY).

## Deprecazioni
- Le funzioni interne con underscore di `src/semantic_onboarding.py` sono considerate deprecated per uso da UI.
- Usare la facade pubblica `semantic.api` per import stabili: `get_paths`, `load_reviewed_vocab`, `convert_markdown`, `enrich_frontmatter`, `write_summary_and_readme`.
- Le chiamate agli underscore generano `DeprecationWarning` a runtime per favorire la migrazione.
