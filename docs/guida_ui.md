# Guida UI di Timmy-KB&#x20;

Questa guida "compatta ma completa" ti accompagna nell'uso dell'interfaccia di Timmy-KB per creare e mantenere una knowledge base a partire da PDF, usando il **mapping Vision-only** (\`semantic\_mapping.yaml\` con \`areas\` e \`system\_folders\`). E' pensata per PM e utenti non tecnici.

---

## 1) Cos'e' e quando usarla

Usa la UI per:

- **Onboarding** di un nuovo cliente/progetto (creazione struttura locale/Drive + mapping).
- **Raccolta e sincronizzazione** PDF (Drive <-> locale) nelle cartelle giuste.
- **Pipeline semantica** (PDF -> Markdown -> arricchimento tag -> README/SUMMARY).
- **Verifica & pubblicazione** (anteprima Docker/HonKit facoltativa).

> La UI e' ideale per il setup iniziale e gli aggiornamenti incrementali (nuovi PDF, nuove aree).

---

## 2) Prerequisiti essenziali

- **Configurazione**: consulta [docs/configurazione.md](configurazione.md) per `.env`, `config/config.yaml`, OIDC e segreti.
- **Software**: Python >= 3.11, Streamlit >= 1.50.0. (Facoltativo: Docker per anteprima, ReportLab per README.pdf)
- **Drive (opzionale ma consigliato)**: Service Account Google con permessi su Drive; ricorda di installare gli extra `pip install .[drive]`.
  - \`DRIVE\_ID\` -> ID del Drive o cartella radice.
  - Installa gli extra Drive: \`pip install .[drive]\`.

**Avvio UI**:

```bash
streamlit run onboarding_ui.py
```
### Accesso rapido alla Guida (sidebar)

Nella **sidebar**, sezione *Azioni rapide*, trovi il pulsante **Guida UI**: apre questa guida **nella stessa scheda** e funziona anche senza uno *slug* cliente attivo. In alternativa, la trovi anche nella barra in alto: **Tools -> Guida UI** (deep-link: `/guida` oppure `?tab=guida`).

> Nota tecnica: la navigazione usa `switch_page` quando disponibile; in fallback aggiorna automaticamente `?tab=guida` e forza il rerun.

---

## 3) Struttura del workspace

Quando crei un cliente (slug \`\`), trovi in locale:

```
output/
+--- timmy-kb-<slug>/
   +--- raw/                # PDF originali (per categoria)
   +--- contrattualistica/  # Documenti legali
   +--- book/               # Markdown generati + indici
   +--- semantic/           # semantic_mapping.yaml, cartelle_raw.yaml, tags*
   +--- config/             # config.yaml, VisionStatement.pdf
   +--- logs/
```

Se Drive e' configurato, la stessa struttura viene replicata sotto **\<DRIVE\_ID>/**.

---

## 4) Onboarding -> **Nuovo cliente** (2 step)

### Step 1 - *Inizializza Workspace*

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
- \`semantic/cartelle\_raw\.yaml\`: albero cartelle per **raw/** + **contrattualistica/**
- \`config/config.yaml\`: dati cliente e (piu' avanti) gli ID Drive.

> Se il PDF e' povero/atipico, rivedi in seguito il mapping via **Settings -> Semantica (YAML)**.

### Step 2 - *Apri workspace*

Provisioning struttura su **Drive**:

- Crea \`/raw\` e \`/contrattualistica\`.
- Crea le **sottocartelle di raw/** dalle **areas** del mapping.
- Carica \`config.yaml\` su Drive e salva localmente gli **ID** (cartella cliente/raw/contrattualistica).

> Lo step 2 **non** rigenera il mapping: serve solo a creare/allineare le cartelle.

---

> ## Pagina Admin – **Configurazione** (`config/config.yaml`)
>
> La pagina **Configurazione** (menu: **Admin → Configurazione**) permette di leggere e modificare in modo guidato il file globale `config/config.yaml`, senza passare da editor esterni.
>
> - **Scope**
>   Le modifiche agiscono sulla configurazione *globale* di Timmy KB (istanza/progetto), non sul singolo workspace cliente.
>   I segreti (token, password, ecc.) restano fuori da questa pagina e continuano a essere gestiti tramite variabili d’ambiente / Secret Manager.
>
> - **Struttura della pagina**
>   Ogni chiave di primo livello del file (`openai`, `vision`, `ui`, `retriever`, `security`, ecc.) viene mostrata come un **box apri/chiudi** con:
>   - un **titolo descrittivo** (es. “OpenAI e LLM”, “Sicurezza e OIDC”…);
>   - una **breve descrizione** che spiega il significato operativo di quella sezione.
>
> - **Modifica dei campi**
>   All’interno di ogni box:
>   - le **sottovoci scalari** (boolean, numeri, stringhe) sono visualizzate come **righe etichetta + input** sulla stessa linea, per facilitare la scansione visiva;
>   - le **sottosezioni annidate** (es. `retriever.throttle`, `security.oidc`) vengono mostrate come piccoli blocchi logici, con le singole opzioni modificate tramite input dedicati;
>   - strutture più complesse (liste o dict profondi) sono editabili tramite una **textarea YAML**: il contenuto viene ri-parsato in automatico quando si salva.
>
> - **Salvataggio e validazione**
>   Il pulsante **“💾 Salva configurazione”**:
>   - serializza lo stato corrente della form in YAML;
>   - sovrascrive `config/config.yaml` usando la scrittura sicura della pipeline (file temporaneo + rename);
>   - in caso di errore di parsing o scrittura mostra un messaggio esplicito a schermo e logga il problema.
>   Non è necessario riavviare l’app Streamlit, ma alcune modifiche potrebbero richiedere un nuovo preflight o un nuovo run del client per avere effetto completo.
>
> - **Quando usare questa pagina**
>   Usa **Configurazione** per:
>   - attivare/disattivare funzionalità globali (es. preflight UI, retriever, logging);
>   - regolare parametri operativi (latenza, parallelismo, timeout, cache);
>   - allineare la configurazione ai diversi ambienti (dev/stage/prod) prima di passare a test o onboarding reali.
>   Per modifiche avanzate o interventi strutturali sul formato del file resta consigliato l’uso di editor dedicati o della pagina **Config Editor**.

---

## Preflight: preferenza persistente vs. bypass "solo questa run"

Nella sezione **Prerequisiti** trovi due controlli distinti:

1. **Salta il controllo** (persistente)
   Aggiorna la preferenza `ui.skip_preflight` in `config/config.yaml`. Da quel momento il preflight viene **saltato** in modo stabile.

2. **Salta il controllo solo per questa esecuzione** (one-shot)
   Bypassa il preflight **solo** nella sessione corrente, senza toccare la preferenza persistente.
   Al primo utilizzo logga l'evento: `ui.preflight.once`.

Comportamento:
- Se la preferenza persistente e' attiva, il preflight non viene eseguito.
- Se non e' attiva, puoi usare il bypass one-shot per test/supporto rapido.
- Il bypass one-shot e' idempotente nella stessa sessione (non riloggato piu' volte).

> Suggerimento: usa il bypass **one-shot** in fase di sviluppo/diagnostica; usa la preferenza **persistente** in ambienti demo o dove il check e' superfluo.

---

## Vocabolario semantico: YAML vs DB

```mermaid
flowchart TD
    A[tags_reviewed.yaml\n(authoring umano)] --> B[Loader YAML\n(validazione + normalizza)]
    B --> C[_derive_tags_db_path(...)\nDeriva percorso DB]
    C --> D[ensure_schema_v2(...)\nEnsure schema v2]
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

> **SSoT runtime:** `tags.db` (SQLite) è la fonte di verità per i tag canonicali. La pipeline interrompe l’esecuzione con `ConfigError` se `semantic/tags.db` risulta mancante o vuoto e la UI lo segnala invitando a rigenerare il vocabolario (`semantic_onboarding`). `tags_reviewed.yaml` rimane esclusivamente un artefatto di authoring (per review umana), mentre tutti i consumatori runtime leggono da `semantic/tags.db`.

## 5) Gestione contenuti -> **Gestisci cliente**

**Albero Drive**: naviga \`\<DRIVE\_ID>/\` e verifica le cartelle.

**Genera README in raw (Drive)** Crea/aggiorna in **ogni sottocartella di ****\`\`**** su Drive** un file guida:

- **Contenuto**: titolo = *ambito* dell'area; corpo = *descrizione*; se disponibili, elenco "Esempi" ricavato da `documents`, `artefatti`, `chunking_hints` e `descrizione_dettagliata.include` del mapping Vision-only.
- **Formato**: `README.pdf` se e' presente ReportLab; altrimenti fallback `README.txt`.
- **Coerenza nomi**: le categorie sono mappate in *kebab-case* (es. `Governance Etica AI` -> `governance-etica-ai`) e devono **corrispondere ai nomi delle cartelle** sotto `raw/`.
- **Idempotente**: se il file esiste viene **aggiornato** (non duplicato); puoi rilanciare dopo ogni modifica al mapping.
- **Prerequisiti**: Drive configurato (`SERVICE_ACCOUNT_FILE`, `DRIVE_ID`) e struttura `<slug>/raw` gia' creata (Step 2 "Apri workspace").
- **Cartelle mancanti**: se una categoria del mapping non ha la relativa cartella su Drive, viene **segnalata e saltata** (non crea la cartella).

**Diff Drive <-> Locale** Confronta i PDF presenti in `<DRIVE_ID>/<slug>/raw/<categoria>/` con quelli in `output/timmy-kb-<slug>/raw/<categoria>/`:

- **Scansione**: lato Drive considera solo `application/pdf`; lato locale considera `*.pdf`.
- **Selezione e download**: scegli i file da copiare e clicca **Scarica PDF da Drive -> locale**. I file vengono salvati **nella stessa categoria**. I file **gia' presenti** non vengono sovrascritti finche' non abiliti il toggle *"Sovrascrivi i file locali in conflitto"* (visibile soltanto quando ci sono conflitti) oppure li rimuovi/rinomini manualmente.
- **Avanzamento**: barra/progresso su **tutti i candidati** (anche quelli gia' presenti); al termine mostra i **nuovi file creati**.
- **README generati**: i `README.pdf` presenti nelle cartelle potrebbero comparire nella lista; **deselezionali** se non ti servono in locale.
- **Rileva PDF in raw/**: riesegue la **sola scansione locale** per aggiornare lo stato (utile se hai copiato manualmente dei file).
- **Cancella cliente**: rimuove l'intero workspace locale e prova a eliminare le cartelle su Drive. Operazione **irreversibile** con conferma.

---

## 6) Pipeline semantica -> **Semantica**

Prima di usare i pulsanti controlla il riquadro **Prerequisiti**:

- **Avvia arricchimento semantico** viene abilitato solo se il servizio `ui.services.tags_adapter` e' disponibile oppure se hai impostato `TAGS_MODE=stub`. In modalita' stub l'azione apre direttamente l'editor YAML senza tentare la pipeline AI.
- **Abilita** (pubblicazione `tags_reviewed.yaml`) resta disattivato se il servizio non e' attivo e non stai usando lo stub; in questo caso la UI mostra l'help per installare l'adapter o abilitare la modalita' stub.
- In modalita' stub lo YAML viene generato da zero (`DEFAULT_TAGS_YAML`) prima dell'import nel DB. Se il DB resta vuoto lo stato cliente torna a **pronto**; se vengono caricati termini passa ad **arricchito** e viene svuotata la cache di gating.
- L'esportazione `tags_reviewed.yaml` richiede che `semantic/tags.db` esista sotto il workspace cliente; il percorso (workspace -> semantic -> YAML/DB) è validato con `ensure_within_and_resolve` prima di scrivere. Eventuali mismatch (DB fuori workspace o `tags.db` diverso) provocano errori di configurazione e impediscono la pubblicazione.

Esegui nell'ordine (ripetibile per nuovi PDF):

1. **Converti PDF -> Markdown**
   - **Cosa fa:** scansiona `raw/<categoria>/**/*.pdf`, esclude file non-PDF/illeggibili, e crea i corrispondenti `.md` in `book/<categoria>/` (rapporto 1:1).
   - **Frontmatter aggiunto:** `title`, `source_category`, `source_file`, `created_at`, `tags_raw` (estratti automatici).
   - **Idempotenza:** genera/aggiorna solo i file nuovi o modificati; non tocca gli altri.
   - **Note/Errore tipico:** PDF protetti o corrotti vengono segnalati nei log e saltati; gli altri proseguono.
2. **Arricchisci frontmatter**
   - **Cosa fa:** trasforma `tags_raw` in `tags` **canonici** leggendo il vocabolario consolidato da `semantic/tags.db` (tramite `semantic.vocab_loader.load_reviewed_vocab`); `semantic_mapping.yaml` è ora solo per l'authoring/review del mapping e non viene usato al runtime. Il DB è lo SSoT dei tag runtime e viene aggiornato prima di ogni arricchimento.
   - **Risultato:** frontmatter dei `.md` aggiornato con `tags` puliti e coerenti (rispettando limiti/score se configurati).
   - **Quando rilanciarlo:** dopo nuove conversioni o dopo modifiche al mapping (keywords/sinonimi/aree).
3. **Genera README/SUMMARY**
   - **SUMMARY.md:** ricostruisce l'indice navigabile di `book/` in base a cartelle e file presenti.
   - **README.md:** crea/aggiorna il README radice e, ove previsto, i README di categoria usando **ambito**/**descrizione** dal mapping.
   - **Idempotenza:** sicuro da rilanciare; modifica solo cio' che e' cambiato.
   - **Sotto il cofano:** i pulsanti richiamano rispettivamente
     `semantic.convert_service.convert_markdown`, `semantic.frontmatter_service.enrich_frontmatter`
     e `semantic.frontmatter_service.write_summary_and_readme`, passando lo stesso `ClientContext`
     della sessione UI. Il vocabolario arriva da `semantic.vocab_loader.load_reviewed_vocab`.
     Se vuoi replicare il comportamento da terminale trovi un esempio completo nella
     [User Guide](user_guide.md#quick-start----terminale-orchestratori).
4. **Anteprima Docker (HonKit)** *(facoltativa)*
   - **Cosa fa:** avvia un container che serve il sito statico generato da `book/`.
   - **Quando usarla:** per QA visivo prima della pubblicazione; chiudi il container al termine.
   - **Log stub:** puoi impostare `PREVIEW_LOG_DIR` con path relativi o assoluti; se il percorso non è raggiungibile la UI mostra un warning con il motivo e salva comunque i log in `logs/preview/` dentro al repository.

- La pagina “Semantica” è accessibile da stato **pronto** in poi (con PDF in `raw/`).
- La **Preview/finishing** resta vincolata agli stati **arricchito/finito**.

---

## 7) Pubblicazione su GitHub -> **CLI / automazioni**

Al momento il push GitHub viene orchestrato dalla CLI (`py src/onboarding_full.py --slug <slug>`), che invoca `pipeline.github_utils.push_output_to_github`. La sequenza e' idempotente e segue tre fasi (`prepare_repo`, `stage_changes`, `push_with_retry` oppure `force_push`), visibili nei log strutturati.

- **Cosa sale su GitHub**: solo i file `.md` presenti in `book/` (gli altri artefatti restano locali).
- **Branch e controlli**: il branch di default deriva da `GIT_DEFAULT_BRANCH`/`DEFAULT_GIT_BRANCH`. I flag `TIMMY_NO_GITHUB` o `SKIP_GITHUB_PUSH` disabilitano il push senza modificare la build. Per i force push serve sia `force_ack` sia un pattern consentito in `GIT_FORCE_ALLOWED_BRANCHES`: l'operazione usa `--force-with-lease`.
- **Sicurezza**: il clone temporaneo vive sotto `output/timmy-kb-<slug>/.push_*` e viene ripulito al termine; `LeaseLock` impedisce push concorrenti sullo stesso workspace.
- **Troubleshooting rapido**: se il token manca o la remote rifiuta l'operazione, i log espongono un `PushError` con l'ultima voce di stderr (`run_cmd.fail`). Per riprodurre in locale puoi usare il test smoke `pytest tests/pipeline/test_github_push.py::test_push_output_to_github_end_to_end_smoke`.

---

## 8) Configurazione avanzata -> **Settings**

**Semantica (YAML)**

- **semantic\_mapping.yaml**: rinomina aree (kebab-case), aggiorna **ambito/descrizione/keywords**.\
  Dopo modifiche, rigenera README (Drive) e, se serve, rifai **Arricchisci**.
- **cartelle\_raw\.yaml**: riflette la struttura di **raw/** + **contrattualistica/**.\
  In scenari standard non toccarlo a mano; se cambi le aree, mantieni coerenza.

**Retriever** (opzionale)

- Parametri di ricerca interna (candidate limit, budget latenza, auto-budget).\
  Lasciali di default salvo esigenze specifiche.

---

## 9) Diagnostics & Log

- Vedi percorsi, conteggi file, ultimi log.
- Scarica zip dei log per supporto.
- Utile se compaiono errori di Drive/AI o conversione.

---

## 10) FAQ / Problemi comuni

- **DRIVE\_ID o SERVICE\_ACCOUNT\_FILE mancanti** -> configura variabili e installa \`.[drive]\`.
- **"Cartella raw non trovata/creata"** -> esegui **Apri workspace** (Step 2).
- **Nessun PDF rilevato** -> carica su Drive e **Scarica**, oppure copia in locale e **Rileva PDF**.
- **README non in PDF** -> manca ReportLab -> viene caricato **README.txt** (comunque ok).
- **Tag strani o mancanti** -> rivedi mapping (aree/keywords/sinonimi), poi **Arricchisci**.
- **Preflight "solo questa run" non ha effetto** -> verifica che **"Salta il controllo" (persistente)** sia **disattivo**; il bypass one-shot non sovrascrive la preferenza salvata. Dopo aver spuntato il one-shot, deve avvenire un **rerun** (la UI lo innesca automaticamente).
- **Il bypass one-shot resta appiccicato tra run** -> il flag e' in `session_state`. Forza un **refresh** o passa `?exit=1` per chiudere la sessione e azzerare lo stato.

---

## 11) Best practice

- Scegli **slug** chiari e stabili (es. \`evagrin\`).
- Carica i PDF **per categoria** (coerenza -> tagging migliore).
- Dopo modifiche al mapping: **Genera README (Drive)** e (se impatta i tag) **Arricchisci**.
- Itera spesso con piccoli lotti di PDF: piu' rapido e sicuro.

---

## 12) Checklist rapida (per sessione)

1. Avvia UI -> seleziona cliente.
2. (Se onboarding): Step 1 **Inizializza** -> Step 2 **Apri workspace**.
3. **Genera README in raw (Drive)** (opzionale ma consigliato).
4. Carica PDF su Drive -> **Scarica** in locale (o **Rileva** se copiati a mano).
5. **Converti** -> **Arricchisci** -> **Genera README/SUMMARY**.
6. (Facoltativo) **Anteprima Docker** -> pubblica.

---

### Glossario minimo

- **Vision-only mapping**: mapping semantico generato dal PDF di Vision (\`areas\`, \`system\_folders\`).
- **raw/**: cartelle con i PDF sorgenti per categoria.
- **book/**: output Markdown e indici.
- **contrattualistica/**: sezione separata per documenti legali.

*Fine.*
