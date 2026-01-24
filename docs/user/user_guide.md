# Timmy-KB - User Guide (v1.0 Beta)

Executive summary

Questo spazio ti accompagna nel comprendere e usare strumenti che mettono a disposizione conoscenze strutturate: l'intento è sostenere la tua lettura e costruzione dei contenuti mantenendo chiara la separazione tra ciò che ti viene proposto e le decisioni che restano tue.

Il sistema non decide per te né nasconde l'incertezza, e non si sostituisce all'esperienza umana; ogni scelta, dubbio o aggiustamento rimane sotto la tua responsabilità, mentre la sua funzione è rendere esplicite le ambiguità e offrirti contesto e chiarezza.

Per la cornice filosofica del progetto vedi [MANIFEST.md](../../MANIFEST.md).

Guida rapida all'onboarding e alla produzione della **KB Markdown AIready**.

## Normative context

Questo progetto adotta una separazione intenzionale tra:
- documentazione tecnica operativa (cartella `docs/`)
- documentazione normativa e di governance ([MANIFEST.md](../../MANIFEST.md), [instructions/](../../instructions/))

Le guide in `docs/` descrivono *come* utilizzare ed estendere il sistema.
I vincoli su *cosa è consentito o vietato*, i ruoli, i gate decisionali e le
macchine a stati sono definiti esclusivamente nelle fonti normative.

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.
> Avvio interfaccia: `streamlit run onboarding_ui.py` (la UI risolve il repo root via SSoT e non si affida a `REPO_ROOT_DIR`).

Nota: la UI e gli orchestratori CLI delegano alle funzioni modulari
`semantic.convert_service`, `semantic.frontmatter_service`,
`semantic.embedding_service` e `semantic.mapping_loader`.

---

## Prerequisiti
- **Python >= 3.11**
- (Opz.) **Docker** per preview HonKit
- (Default Drive) **Service Account JSON** e `DRIVE_ID`

Variabili utili: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `LOG_REDACTION`.

---

## Quickstart

Per un avvio essenziale vedi anche [quickstart](quickstart.md).

### Avvio rapido UI
1. `streamlit run onboarding_ui.py`
2. Inserisci **slug** e **nome cliente**.
3. Drive: crea struttura, genera README, scarica PDF in `raw/`.
4. `python -m timmy_kb.cli.raw_ingest --slug <slug>` (genera `normalized/`).
5. Semantica: **Converti** -> **Arricchisci** -> **README & SUMMARY**.
6. (Opz.) **Preview Docker**.

### Avvio rapido CLI
1. `python -m timmy_kb.cli.pre_onboarding --slug <slug> --name "<Cliente>"`
2. `python -m timmy_kb.cli.raw_ingest --slug <slug>`
3. `python -m timmy_kb.cli.tag_onboarding --slug <slug> --proceed`
4. `py src/kg_build.py --slug <slug>`
5. `python -m timmy_kb.cli.semantic_onboarding --slug <slug>`
6. (Opz.) **Preview Docker**.

### Cosa succede in 10 minuti
- Crea workspace e config cliente.
- Genera mapping Vision-only e struttura Drive.
- Scarica PDF in `raw/` e genera `normalized/`.
- Converte i Markdown normalizzati e arricchisce frontmatter.
- Ricostruisce `README.md`/`SUMMARY.md` e abilita la preview.

## Uso tramite UI (Streamlit)

Questa guida "compatta ma completa" ti accompagna nell'uso dell'interfaccia di Timmy-KB per creare e mantenere una knowledge base a partire da PDF, usando il **mapping Vision-only** (\`semantic\_mapping.yaml\` con \`areas\` e \`system\_folders\`). E' pensata per PM e utenti non tecnici.

---

### 1) Cos'e' e quando usarla

Usa la UI per:

- **Onboarding** di un nuovo cliente/progetto (creazione struttura locale/Drive + mapping).
- **Raccolta e sincronizzazione** PDF (Drive <-> locale) nelle cartelle giuste.
- **Pipeline semantica** (raw -> normalized -> book -> arricchimento tag -> README/SUMMARY).
- **Verifica & pubblicazione** (anteprima Docker/HonKit facoltativa).

> La UI e' ideale per il setup iniziale e gli aggiornamenti incrementali (nuovi PDF, nuove aree).

---

### 2) Prerequisiti essenziali

- **Configurazione**: consulta [docs/configurazione.md](../configurazione.md) per `.env`, `config/config.yaml`, OIDC e segreti.
- **Software**: Python >= 3.11, Streamlit >= 1.50.0. (Facoltativo: Docker per anteprima, ReportLab per README.pdf)
- **Allineamento installazione**: il preflight verifica che i moduli pipeline siano importabili dallo stesso root della UI. Se segnala mismatch, attiva il venv corretto ed esegui `pip install -e .` dalla root del repo.
- **Drive (opzionale ma consigliato)**: Service Account Google con permessi su Drive; ricorda di installare gli extra `pip install .[drive]`.
  - \`DRIVE\_ID\` -> ID del Drive o cartella radice.
  - Installa gli extra Drive: \`pip install .[drive]\`.

**Avvio UI**:

```powershell
streamlit run onboarding_ui.py
```

Il file `onboarding_ui.py` risolve la directory del repository via SSoT e non si affida a `REPO_ROOT_DIR`, quindi non serve piu un wrapper: Streamlit viene eseguito direttamente dal repo e la pipeline scrive/legge i workspace sotto `output/timmy-kb-<slug>`.
#### Accesso rapido alla Guida (sidebar)

Nella **sidebar**, sezione *Azioni rapide*, trovi il pulsante **Guida UI**: apre questa guida **nella stessa scheda** e funziona anche senza uno *slug* cliente attivo. In alternativa, la trovi anche nella barra in alto: **Tools -> Guida UI** (deep-link: `/guida` oppure `?tab=guida`).

> Nota tecnica: la navigazione usa `switch_page` quando disponibile; in fallback aggiorna automaticamente `?tab=guida` e forza il rerun. Segnale: nessun segnale/log esplicito documentato.
> Routing attuale: `st.Page` + `st.navigation` (UI index); evitati hack su query params/`switch_page`.

---

### 3) Struttura del workspace

Quando crei un cliente (slug \`\`), trovi in locale:

```
output/
+--- timmy-kb-<slug>/
   +--- raw/                # PDF originali (per categoria)
   +--- normalized/         # Markdown normalizzati (derivati)
   +--- contrattualistica/  # Documenti legali
   +--- book/               # Markdown generati + indici
   +--- semantic/           # semantic_mapping.yaml, tags*
   +--- config/             # config.yaml, VisionStatement.pdf
   +--- logs/
```

Se Drive e' configurato, la stessa struttura viene replicata sotto **\<DRIVE\_ID>/**.

Template seed: nessun template semantico viene copiato nel workspace da `pre_onboarding`.

---

### 4) Onboarding -> **Nuovo cliente** (2 step)

#### Step 1 - *Inizializza Workspace*

Compila:

- **Slug** (obbligatorio, kebab-case, es. \`acme\`).
- **Nome cliente** (facoltativo).
- **VisionStatement.pdf** (obbligatorio): la Vision/mission/contesto del cliente.

Cosa produce:

- \`semantic/semantic\_mapping.yaml\` (**Vision-only**: usa \`areas\` + \`system\_folders\
  ").trim()

) con:

- **areas**: chiave -> { ambito, descrizione, (keywords opzionali) }
- **system\_folders**: sezioni fisse (es. identity/vision/mission/glossario...)
- \`config/config.yaml\`: dati cliente e (piu' avanti) gli ID Drive.

> Se il PDF e' povero/atipico, rivedi in seguito il mapping via **Settings -> Semantica (YAML)**.

#### Step 2 - *Apri workspace*

Provisioning struttura su **Drive**:

- Crea \`/raw\` e \`/contrattualistica\`.
- Carica \`config.yaml\` su Drive e salva localmente gli **ID** (cartella cliente/raw/contrattualistica).

> Lo step 2 **non** rigenera il mapping: serve solo a creare/allineare le cartelle.

---

> ## Pagina Admin  **Configurazione** (`config/config.yaml`)
>
> La pagina **Configurazione** (menu: **Admin  Configurazione**) permette di leggere e modificare in modo guidato il file globale `config/config.yaml`, senza passare da editor esterni.
>
> - **Scope**
>   Le modifiche agiscono sulla configurazione *globale* di Timmy KB (istanza/progetto), non sul singolo workspace cliente.
>   I segreti (token, password, ecc.) restano fuori da questa pagina e continuano a essere gestiti tramite variabili d'ambiente / Secret Manager.
>
> - **Struttura della pagina**
>   Ogni chiave di primo livello del file (`openai`, `vision`, `ui`, `retriever`, `security`, ecc.) viene mostrata come un **box apri/chiudi** con:
>   - un **titolo descrittivo** (es. OpenAI e LLM, Sicurezza e OIDC...);
>   - una **breve descrizione** che spiega il significato operativo di quella sezione.
>
> - **Modifica dei campi**
>   Allinterno di ogni box:
>   - le **sottovoci scalari** (boolean, numeri, stringhe) sono visualizzate come **righe etichetta + input** sulla stessa linea, per facilitare la scansione visiva;
>   - le **sottosezioni annidate** (es. `retriever.throttle`, `security.oidc`) vengono mostrate come piccoli blocchi logici, con le singole opzioni modificate tramite input dedicati;
>   - strutture piu complesse (liste o dict profondi) sono editabili tramite una **textarea YAML**: il contenuto viene ri-parsato in automatico quando si salva.
>
> - **Salvataggio e validazione**
>   Il pulsante ** Salva configurazione**:
>   - serializza lo stato corrente della form in YAML;
>   - sovrascrive `config/config.yaml` usando la scrittura sicura della pipeline (file temporaneo + rename);
>   - in caso di errore di parsing o scrittura mostra un messaggio esplicito a schermo e logga il problema.
>   Non e necessario riavviare lapp Streamlit, ma alcune modifiche potrebbero richiedere un nuovo preflight o un nuovo run del client per avere effetto completo.
>
> - **Quando usare questa pagina**
>   Usa **Configurazione** per:
>   - attivare/disattivare funzionalita globali (es. preflight UI, retriever, logging);
>   - regolare parametri operativi (latenza, parallelismo, timeout, cache);
>   - allineare la configurazione ai diversi ambienti (dev/stage/prod) prima di passare a test o onboarding reali.
>   Per modifiche avanzate o interventi strutturali sul formato del file resta consigliato l'uso di editor dedicati o della pagina **Config Editor**.

---

### Vocabolario semantico: YAML vs DB

```mermaid
flowchart TD
    A[tags_reviewed.yaml
(authoring umano)] --> B[Loader YAML
(validazione + normalizza)]
    B --> C[_derive_tags_db_path(...)
Deriva percorso DB]
    C --> D[ensure_schema_v2(...)
Ensure schema v2]
    D --> E[Upsert terms]
    D --> F[Upsert folders]
    E --> G[folder_terms]
    F --> G
    G --> H[tags.db]
    H --> I[UI/Pipeline runtime]
```

| Campo YAML | Destinazione DB               | Note                              |
|------------|------------------------------|-----------------------------------|
| `canonical` | `terms.canonical`            | lowercase + trim                  |
| `aliases[]` | (merge in memoria)           | confluiscono sul canonical        |
| `folders[]` | `folders.path`               | path relativi e normalizzati      |
| Link folder/tag | `folder_terms(..., weight)` | `weight` opzionale (default 1.0) |

> Pseudocode ingestion: vedi `storage.tags_store.import_tags_yaml_to_db`.

> **SSoT runtime:** `tags.db` (SQLite) e la fonte di verita per i tag canonicali. La pipeline interrompe lesecuzione con `ConfigError` se `semantic/tags.db` risulta mancante o vuoto e la UI lo segnala invitando a rigenerare il vocabolario (`semantic_onboarding`). `tags_reviewed.yaml` rimane esclusivamente un artefatto di authoring (per review umana), mentre tutti i consumatori runtime leggono da `semantic/tags.db`.

### 5) Gestione contenuti -> **Gestisci cliente**

**Nota operativa**: prima di lanciare gli arricchimenti assicurati che `normalized/` contenga i Markdown (genera via `raw_ingest` dopo aver scaricato i PDF in `raw/`). Se modifichi le cartelle locali oppure `tags_reviewed.yaml`, premi il pulsante **Ricarica vista Gestisci cliente** (in alto) per rinfrescare i controlli ed evitare stati incoerenti.

Le azioni principali sono raggruppate in expander distinti: `Scarica PDF da Drive  locale`, `Arricchimento semantico + revisione tags`, `Genera README in raw (Drive)`. Nella sezione centrale viene anche mostrato quale backend NLP e attivo (`TAGS_NLP_BACKEND`, SpaCy di default) e viene ricordato che l'euristica viene sempre eseguita in aggiunta.


**Albero Drive**: naviga \`\<DRIVE\_ID>/\` e verifica le cartelle.

**Genera README in raw (Drive)** Crea/aggiorna in **ogni sottocartella di ****\`\`**** su Drive** un file guida:

- **Contenuto**: titolo = *ambito* dell'area; corpo = *descrizione*; se disponibili, elenco "Esempi" ricavato da `documents`, `artefatti`, `chunking_hints` e `descrizione_dettagliata.include` del mapping Vision-only.
- **Formato**: `README.pdf` se e' presente ReportLab; altrimenti fallback `README.txt`. Segnale: nessun segnale/log esplicito documentato.
- **Coerenza nomi**: le categorie sono mappate in *kebab-case* (es. `Governance Etica AI` -> `governance-etica-ai`) e devono **corrispondere ai nomi delle cartelle** sotto `raw/`.
- **Idempotente**: se il file esiste viene **aggiornato** (non duplicato); puoi rilanciare dopo ogni modifica al mapping.
- **Prerequisiti**: Drive configurato (`SERVICE_ACCOUNT_FILE`, `DRIVE_ID`) e struttura `<slug>/raw` gia' creata (Step 2 "Apri workspace").
- **Cartelle mancanti**: se una categoria del mapping non ha la relativa cartella su Drive, viene **segnalata e saltata** (non crea la cartella).

**Diff Drive <-> Locale** Confronta i PDF presenti in `<DRIVE_ID>/<slug>/raw/<categoria>/` con quelli in `output/timmy-kb-<slug>/raw/<categoria>/`:

- **Scansione**: lato Drive considera solo `application/pdf`; lato locale considera `*.pdf`.
- **Selezione e download**: scegli i file da copiare e clicca **Scarica PDF da Drive -> locale**. I file vengono salvati **nella stessa categoria**. I file **gia' presenti** non vengono sovrascritti finche' non abiliti il toggle *"Sovrascrivi i file locali in conflitto"* (visibile soltanto quando ci sono conflitti) oppure li rimuovi/rinomini manualmente.
- **Avanzamento**: barra/progresso su **tutti i candidati** (anche quelli gia' presenti); al termine mostra i **nuovi file creati**.
- **README generati**: i `README.pdf` presenti nelle cartelle potrebbero comparire nella lista; **deselezionali** se non ti servono in locale. La sincronizzazione locale (espander "Scarica PDF da Drive -> locale") scarica **solo i PDF** e lascia i README su Drive.
- **Rileva PDF in raw/**: riesegue la **sola scansione locale** per aggiornare lo stato (utile se hai copiato manualmente dei file).
- **Cancella cliente**: il cleanup (rimozione workspace locale/Drive/DB) e ora controllato nella pagina **Config Editor** (Tools  Configurazione); si apre un wizard con conferma prima di applicare la cancellazione.

---

### 6) Pipeline semantica -> **Semantica**

Prima di usare i pulsanti controlla il riquadro **Prerequisiti**:

- **Avvia arricchimento semantico** viene abilitato solo se il servizio `ui.services.tags_adapter` e' disponibile oppure se hai impostato `TAGS_MODE=stub`. In modalita' stub l'azione apre direttamente l'editor YAML senza tentare la pipeline AI.
- **Abilita** (pubblicazione `tags_reviewed.yaml`) resta disattivato se il servizio non e' attivo e non stai usando lo stub; in questo caso la UI mostra l'help per installare l'adapter o abilitare la modalita' stub.
- In modalita' stub lo YAML viene generato da zero (`DEFAULT_TAGS_YAML`) prima dell'import nel DB. Se il DB resta vuoto lo stato cliente torna a **pronto**; se vengono caricati termini passa ad **arricchito** e viene svuotata la cache di gating.
- L'esportazione `tags_reviewed.yaml` richiede che `semantic/tags.db` esista sotto il workspace cliente; il percorso (workspace -> semantic -> YAML/DB) e validato con `ensure_within_and_resolve` prima di scrivere. Eventuali mismatch (DB fuori workspace o `tags.db` diverso) provocano errori di configurazione e impediscono la pubblicazione.

Esegui nell'ordine (ripetibile per nuovi PDF):
Prerequisito: `normalized/` deve essere pronta (generata da `raw_ingest`).

1. **Converti Markdown normalizzati -> book**
   - **Cosa fa:** scansiona `normalized/**/*.md`, esclude file illeggibili, e crea i corrispondenti `.md` in `book/` (rapporto 1:1).
   - **Frontmatter aggiunto:** `title`, `source_category`, `source_file`, `created_at`, `tags_raw` (estratti automatici).
   - **Idempotenza:** genera/aggiorna solo i file nuovi o modificati; non tocca gli altri.
   - **Note/Errore tipico:** Markdown vuoti o fuori perimetro vengono segnalati nei log e saltati; gli altri proseguono.
2. **Arricchisci frontmatter**
   - **Cosa fa:** trasforma `tags_raw` in `tags` **canonici** leggendo il vocabolario consolidato da `semantic/tags.db` (tramite `semantic.vocab_loader.load_reviewed_vocab`); `semantic_mapping.yaml` e ora solo per l'authoring/review del mapping e non viene usato al runtime. Il DB e lo SSoT dei tag runtime e viene aggiornato prima di ogni arricchimento.
   - **Risultato:** frontmatter dei `.md` aggiornato con `tags` puliti e coerenti (rispettando limiti/score se configurati).
   - **Telemetria:** l'arricchimento emette `semantic.book.frontmatter` con il numero di file aggiornati (UI/CLI).
   - **Entita e relazioni:** se in `semantic/tags.db` sono presenti entita con `status=approved` nella tabella `doc_entities` (proposte da SpaCy a partire dalle entita definite in `semantic_mapping.yaml`), il frontmatter viene arricchito anche con le chiavi `entities` e `relations_hint`, rendendo esplicite le entita e le relazioni del mapping Vision-only.
    - **Quando rilanciarlo:** dopo nuove conversioni o dopo modifiche al mapping (keywords/sinonimi/aree).
> **DIKW in azione:** i PDF in `raw/` (derivati in `normalized/`) piu i tag grezzi rappresentano i **Data**, la conversione normalized->book piu l'arricchimento frontmatter diventano **Information**, la generazione di `README/SUMMARY` struttura la **Knowledge** dentro `book/`, e l'anteprima Docker e la vista finale sulla Knowledge disponibile.

3. **Costruisci il Knowledge Graph dei tag (Tag KG Builder)**
    - **Cosa fa:** legge `semantic/tags_raw.json`, invoca la tool call `build_tag_kg` con namespace (puoi scegliere di usare lo slug o un valore custom), e pubblica `semantic/kg.tags.json` + `semantic/kg.tags.md`.
    - **Output:** `kg.tags.json` (machine-first) piu `kg.tags.md` (human-friendly) utilizzati dal team per revisioni e prossimi ingest/embedding.
    - **Quando rilanciarlo:** dopo aver generato/aggiornato i tag raw (o quando serve una nuova versione del grafo).
    - **Dove:** usa il pannello *Knowledge Graph dei tag* nella pagina **Gestisci cliente** oppure il CLI dedicato `py src/kg_build.py --slug <slug>` (lo step e idempotente finche `tags_raw.json` non cambia).
4. **Genera README/SUMMARY**
   - **SUMMARY.md:** ricostruisce l'indice navigabile di `book/` in base a cartelle e file presenti.
   - **README.md:** crea/aggiorna il README radice e, ove previsto, i README di categoria usando **ambito**/**descrizione** dal mapping.
   - **Idempotenza:** sicuro da rilanciare; modifica solo cio' che e' cambiato.
   - **Sotto il cofano:** i pulsanti richiamano rispettivamente
     `semantic.convert_service.convert_markdown`, `semantic.frontmatter_service.enrich_frontmatter`
     e `semantic.frontmatter_service.write_summary_and_readme`, passando lo stesso `ClientContext`
     della sessione UI. Il vocabolario arriva da `semantic.vocab_loader.load_reviewed_vocab`.
     Se vuoi replicare il comportamento da terminale trovi un esempio completo nella
     [User Guide](user_guide.md#quick-start----terminale-orchestratori).
   - **Gating preview:** la UI invoca `semantic.book_readiness.check_book_dir` per assicurarsi che `book/` contenga `README.md`, `SUMMARY.md` e almeno un file Markdown di contenuto prima di abilitare la preview Docker; ora la disponibilita della preview riflette la **Knowledge** pronta anziche la sola presenza di file in `normalized/`.
4. **Anteprima Docker (HonKit)** *(facoltativa)*
   - **Cosa fa:** avvia un container che serve il sito statico generato da `book/`.
   - **Quando usarla:** per QA visivo prima della pubblicazione; chiudi il container al termine.
   - **Log stub:** imposta `PREVIEW_LOG_DIR` con path relativi o assoluti. Se il percorso non esiste o non e scrivibile la preview si ferma con errore esplicito (nessun fallback).

- La pagina Semantica e accessibile da stato **pronto** in poi (con Markdown in `normalized/`).
- La **Preview/finishing** resta vincolata agli stati **arricchito/finito**.

---

### 7) Configurazione avanzata -> **Settings**

**Semantica (YAML)**

- **semantic\_mapping.yaml**: rinomina aree (kebab-case), aggiorna **ambito/descrizione/keywords**.\
  Dopo modifiche, rigenera README (Drive) e, se serve, rifai **Arricchisci**.
- **cartelle\_raw\.yaml**: riflette la struttura di **raw/** + **contrattualistica/**.\
  In scenari standard non toccarlo a mano; se cambi le aree, mantieni coerenza.

> **Cleanup:** la cancellazione guidata del workspace (locale + Drive) si trova ora nella pagina **Config Editor** (Tools  Configurazione); usa il pulsante Cancella cliente... in fondo per avviare il wizard irreversibile con conferma.

**Retriever** (opzionale)

- Parametri di ricerca interna (candidate limit, budget latenza, auto-budget).\
  Lasciali di default salvo esigenze specifiche.

---

### 9) Diagnostics & Log

- Vedi percorsi, conteggi file, ultimi log.
- Scarica zip dei log per supporto.
- Utile se compaiono errori di Drive/AI o conversione.

---

### 10) FAQ / Problemi comuni

- **DRIVE\_ID o SERVICE\_ACCOUNT\_FILE mancanti** -> configura variabili e installa \`.[drive]\`.
- **"Cartella raw non trovata/creata"** -> esegui **Apri workspace** (Step 2).
- **Nessun PDF rilevato** -> carica su Drive e **Scarica**, oppure copia in locale e **Rileva PDF**.
- **README non in PDF** -> manca ReportLab -> viene caricato **README.txt** (comunque ok).
- **Tag strani o mancanti** -> rivedi mapping (aree/keywords/sinonimi), poi **Arricchisci**.
### 11) Best practice

- Scegli **slug** chiari e stabili (es. \`evagrin\`).
- Carica i PDF **per categoria** (coerenza -> tagging migliore).
- Dopo modifiche al mapping: **Genera README (Drive)** e (se impatta i tag) **Arricchisci**.
- Itera spesso con piccoli lotti di PDF: piu' rapido e sicuro.

---

### 12) Checklist rapida (per sessione)

1. Avvia UI -> seleziona cliente.
2. (Se onboarding): Step 1 **Inizializza** -> Step 2 **Apri workspace**.
3. **Genera README in raw (Drive)** (opzionale ma consigliato).
4. Carica PDF su Drive -> **Scarica** in locale (o **Rileva** se copiati a mano).
5. `python -m timmy_kb.cli.raw_ingest --slug <slug>` (genera `normalized/`).
6. **Converti** -> **Arricchisci**.
7. **Costruisci il Knowledge Graph dei tag** (UI o `kg_build.py`).
8. **Genera README/SUMMARY**.
9. (Facoltativo) **Anteprima Docker** -> pubblica.

---

#### Glossario minimo

- **Vision-only mapping**: mapping semantico generato dal PDF di Vision (\`areas\`, \`system\_folders\`).
- **raw/**: cartelle con i PDF sorgenti per categoria.
- **normalized/**: Markdown normalizzati derivati dai PDF.
- **book/**: output Markdown e indici.
- **contrattualistica/**: sezione separata per documenti legali.

*Fine.*

## From Foundation to Agency
- La fase iniziale coinvolge ProtoTimmy che governa la pipeline di foundation: l'obiettivo è produrre markdown semanticamente arricchiti e validare il knowledge graph.
- Completare questa pipeline foundation abilita il passaggio a Timmy, che assume agency dialogica e coordina Domain Gatekeepers e micro-agent nella Prompt Chain documentata in `instructions/`.
- La pipeline non orchestra né decide: fornisce gli artifact affidabili richiesti dallo SSoT, mentre Timmy è responsabile della governance e del dialogo con i gatekeeper dopo la validazione.

---

## Quick start    Terminale (orchestratori)
Esegui gli step in sequenza.

```bash
# 1) Setup locale (+ Drive opzionale)
python -m timmy_kb.cli.pre_onboarding --slug acme --name "Cliente ACME"

# 2) Normalizzazione RAW -> normalized
python -m timmy_kb.cli.raw_ingest --slug acme

# 3) Tagging semantico (default: Drive)
python -m timmy_kb.cli.tag_onboarding --slug acme --proceed

# 4) Costruzione Knowledge Graph dei tag
py src/kg_build.py --slug acme

> Nota: `timmy_kb.cli.semantic_onboarding` invoca internamente `build_kg_for_workspace`,
> quindi l'intero flusso semantic costruisce automaticamente il Tag KG prima di
> generare README/SUMMARY. La CLI `kg_build.py` serve per ricostruire o isolare
> questo step quando necessario.

# 5) Conversione + arricchimento + README/SUMMARY (+ preview opz.)
Esegui la pipeline semantica con gli helper modulari; ricava i path dal `WorkspaceLayout` (SSoT).

```bash
python - <<'PY'
from pathlib import Path

from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from pipeline.workspace_layout import WorkspaceLayout
from semantic.convert_service import convert_markdown
from semantic.frontmatter_service import enrich_frontmatter, write_summary_and_readme
from semantic.vocab_loader import load_reviewed_vocab

slug = "acme"
ctx = ClientContext.load(slug=slug, require_env=True, bootstrap_config=False)
layout = WorkspaceLayout.from_context(ctx)
repo_root_dir = layout.repo_root_dir
log = get_structured_logger("docs.semantic", context={"slug": slug})

convert_markdown(ctx, log, slug=slug)
vocab = load_reviewed_vocab(repo_root_dir, log)
enrich_frontmatter(ctx, log, vocab, slug=slug, allow_empty_vocab=True)
write_summary_and_readme(ctx, log, slug=slug)
PY
```

> **Nota**: `python -m timmy_kb.cli.semantic_onboarding` e `python -m timmy_kb.cli.semantic_headless` falliscono con `ConfigError` quando `semantic/tags.db` e mancante o vuoto; rigenera il vocabolario eseguendo `python -m timmy_kb.cli.tag_onboarding --slug <slug> --proceed`.

(Puoi continuare a usare `python -m timmy_kb.cli.semantic_onboarding` come orchestratore
della sequenza se preferisci una CLI dedicata.)

Per l'indicizzazione nel DB semantico puoi delegare a
`semantic.embedding_service.index_markdown_to_db`, passando il client embeddings
adottato nel tuo ambiente (es. quello configurato nella UI retriever).

# 4) Preview finale (HonKit locale)
La preview Docker/HonKit è gestita via adapter/UI; il modulo esiste ma non è previsto/supportato come entrypoint pubblico `python -m pipeline.honkit_preview` (vedi runbook).

Modalita` **batch** (senza prompt): aggiungi `--non-interactive` ai comandi sopra per la parte CLI di onboarding.

---

## Vision Statement (CLI)
1. Copia `VisionStatement.pdf` in `output/timmy-kb-<slug>/config/` oppure in `raw/`.
2. Assicurati che `.env` contenga `OPENAI_API_KEY` (token valido per il modello Vision).
3. Esegui `py tools/gen_vision_yaml.py --slug <slug>`: il tool carica l'ambiente, risolve i path e genera
   `semantic/semantic_mapping.yaml`.
4. Errori (PDF mancante, risposta vuota, rifiuto modello) sono riportati come `ConfigError` senza stack trace.

### Entita fondamentali e codici documentali
- **Operativi:** Progetto, Obiettivo, Milestone, Epic, Task, Processo, Deliverable
- **Attori:** Organizzazione, Cliente, Stakeholder, Team, Operatore, Decisore, Management, Fornitore
- **Azioni:** Decisione, Analisi, Modifica, Intervento, Upgrade, Downgrade, Validazione
- **Oggetti:** Bene, Servizio, Skill, Risorsa, Outsourcing, Documento, Contratto, Dataset

| Categoria   | Entita        | Codice suggerito | Esempio nome file                     |
|-------------|---------------|------------------|---------------------------------------|
| Operativo   | Progetto      | PRJ-             | PRJ-Progetto_neXT_roadmap.pdf         |
| Attore      | Organizzazione| ORG-             | ORG-Statuto_NeXT_srl.pdf              |
| Oggetto     | Contratto     | CTR-             | CTR-Contratto_servizi_AI_2025.pdf     |
| Azione      | Decisione     | DEC-             | DEC-Verbale_CDA_2025-01-15.pdf        |

I prefissi non sono decorativi: servono a collegare i file alle entita, alimentare il modello ER e migliorare ricerca/tagging ed embedding. Se cambi entita o strutture, aggiorna il Vision Statement e riesegui la funzione Vision per rigenerare mapping/ER.


## Struttura output
```
output/timmy-kb-<slug>/
   raw/        # PDF
   normalized/ # Markdown normalizzati
   book/       # Markdown + SUMMARY.md + README.md
   semantic/   # semantic_mapping.yaml, tags_raw.csv, tags.db
   config/     # config.yaml (con eventuali ID Drive)
   logs/
```

Template seed (repo): nessun template semantico copiato nel workspace durante `pre_onboarding`.

---

## Note operative
- **normalized/ e` la sorgente** per conversione/enrichment; raw/ e Drive restano l'evidenza di ingest.
- Solo file **.md** in `book/` vengono pubblicati; i `.md.fp` sono ignorati.
- Log con redazione automatica se `LOG_REDACTION` e` attivo.
- I pulsanti **Avvia arricchimento semantico**/**Abilita** nella UI rispettano il servizio `ui.services.tags_adapter`: se non e` disponibile vengono disabilitati (salvo `TAGS_MODE=stub`). In modalita` stub lo YAML viene rigenerato con `DEFAULT_TAGS_YAML` e lo stato cliente torna a **pronto** se il DB resta vuoto.
- La preview finale usa HonKit via Docker ed è gestita via adapter/UI; il modulo esiste ma non è previsto/supportato come entrypoint pubblico `python -m pipeline.honkit_preview` (vedi runbook).

## Impostazioni retriever (UI)
La sidebar della UI consente di configurare il retriever, salvando i parametri in `config/config.yaml`:

```yaml
retriever:
  auto_by_budget: false
  throttle:
    candidate_limit: 4000
    latency_budget_ms: 300
    parallelism: 1
    sleep_ms_between_calls: 0
```

La UI applica immediatamente le modifiche e i test di regressione coprono il pass-through verso gli helper di `semantic.embedding_service`.

---
## Controllo caratteri & encoding (UTF-8)

- `fix-control-chars`: hook pre-commit che normalizza i file (rimozione controlli C0/C1 + NFC).
- `forbid-control-chars`: hook pre-commit di guardia; blocca il commit se restano caratteri proibiti o file non UTF-8.

Esecuzione manuale:

```bash
pre-commit run fix-control-chars --all-files
pre-commit run forbid-control-chars --all-files
python tools/forbid_control_chars.py --fix <path>
```

## Troubleshooting essenziale
- `DRIVE_ID` mancante  lo richiede `pre_onboarding`/`raw_ingest`/`tag_onboarding` (default Drive).
- PDF non scaricati in UI  assicurati di aver prima **generato i README** in `raw/` e di avere permessi Drive corretti.
- Preview non parte  verifica Docker e porta libera.
- Conversione fallisce con "solo Markdown non sicuri/fuori perimetro"  in `normalized/` ci sono solo symlink o percorsi fuori dal perimetro sicuro. Rimuovi i symlink o sposta i file reali dentro `normalized/`, quindi riprova la conversione.

## Limiti e vincoli della Beta 1.0
Alcune limitazioni del flusso non sono bug ma scelte deliberate
di governance e auditabilita'.

In particolare, la distinzione tra Strict Mode e Dummy Mode
e' descritta nella guida operativa dedicata:
[Strict vs Dummy - Guida Operativa](../strict_vs_dummy_beta.md).
