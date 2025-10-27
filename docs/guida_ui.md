# Guida UI di Timmy‑KB&#x20;

Questa guida “compatta ma completa” ti accompagna nell’uso dell’interfaccia di Timmy‑KB per creare e mantenere una knowledge base a partire da PDF, usando il **mapping Vision‑only** (\`semantic\_mapping.yaml\` con \`areas\` e \`system\_folders\`). È pensata per PM e utenti non tecnici.

---

## 1) Cos’è e quando usarla

Usa la UI per:

- **Onboarding** di un nuovo cliente/progetto (creazione struttura locale/Drive + mapping).
- **Raccolta e sincronizzazione** PDF (Drive ⇄ locale) nelle cartelle giuste.
- **Pipeline semantica** (PDF → Markdown → arricchimento tag → README/SUMMARY).
- **Verifica & pubblicazione** (anteprima Docker/HonKit facoltativa).

> La UI è ideale per il setup iniziale e gli aggiornamenti incrementali (nuovi PDF, nuove aree).

---

## 2) Prerequisiti essenziali

- **Software**: Python ≥ 3.11, Streamlit ≥ 1.50.0. (Facoltativo: Docker per anteprima, ReportLab per README.pdf)
- **Drive (opzionale ma consigliato)**: Service Account Google con permessi su Drive; variabili d’ambiente:
  - \`SERVICE\_ACCOUNT\_FILE\` → path al JSON delle credenziali.
  - \`DRIVE\_ID\` → ID del Drive o cartella radice.
  - Installa gli extra Drive: \`pip install .[drive]\`.

**Avvio UI**:

```bash
streamlit run onboarding_ui.py
```

---

## 3) Struttura del workspace

Quando crei un cliente (slug \`\`), trovi in locale:

```
output/
└─ timmy-kb-<slug>/
   ├─ raw/                # PDF originali (per categoria)
   ├─ contrattualistica/  # Documenti legali
   ├─ book/               # Markdown generati + indici
   ├─ semantic/           # semantic_mapping.yaml, cartelle_raw.yaml, tags*
   ├─ config/             # config.yaml, VisionStatement.pdf
   └─ logs/
```

Se Drive è configurato, la stessa struttura viene replicata sotto **\<DRIVE\_ID>/**.

---

## 4) Onboarding → **Nuovo cliente** (2 step)

### Step 1 — *Inizializza Workspace*

Compila:

- **Slug** (obbligatorio, kebab-case, es. \`acme\`).
- **Nome cliente** (facoltativo).
- **VisionStatement.pdf** (obbligatorio): la Vision/mission/contesto del cliente.

Cosa produce:

- \`semantic/semantic\_mapping.yaml\` (**Vision‑only**: usa \`areas\` + \`system\_folders\
  ").trim()

) con:

- **areas**: chiave → { ambito, descrizione, (keywords opzionali) }
- **system\_folders**: sezioni fisse (es. identity/vision/mission/glossario…)
- \`semantic/cartelle\_raw\.yaml\`: albero cartelle per **raw/** + **contrattualistica/**
- \`config/config.yaml\`: dati cliente e (più avanti) gli ID Drive.

> Se il PDF è povero/atipico, rivedi in seguito il mapping via **Settings → Semantica (YAML)**.

### Step 2 — *Apri workspace*

Provisioning struttura su **Drive**:

- Crea \`/raw\` e \`/contrattualistica\`.
- Crea le **sottocartelle di raw/** dalle **areas** del mapping.
- Carica \`config.yaml\` su Drive e salva localmente gli **ID** (cartella cliente/raw/contrattualistica).

> Lo step 2 **non** rigenera il mapping: serve solo a creare/allineare le cartelle.

---

## 5) Gestione contenuti → **Gestisci cliente**

**Albero Drive**: naviga \`\<DRIVE\_ID>/\` e verifica le cartelle.

**Genera README in raw (Drive)** Crea/aggiorna in **ogni sottocartella di ****\`\`**** su Drive** un file guida:

- **Contenuto**: titolo = *ambito* dell’area; corpo = *descrizione*; se disponibili, elenco “Esempi” ricavato da `documents`, `artefatti`, `chunking_hints` e `descrizione_dettagliata.include` del mapping Vision‑only.
- **Formato**: `README.pdf` se è presente ReportLab; altrimenti fallback `README.txt`.
- **Coerenza nomi**: le categorie sono mappate in *kebab‑case* (es. `Governance Etica AI` → `governance-etica-ai`) e devono **corrispondere ai nomi delle cartelle** sotto `raw/`.
- **Idempotente**: se il file esiste viene **aggiornato** (non duplicato); puoi rilanciare dopo ogni modifica al mapping.
- **Prerequisiti**: Drive configurato (`SERVICE_ACCOUNT_FILE`, `DRIVE_ID`) e struttura `<slug>/raw` già creata (Step 2 “Apri workspace”).
- **Cartelle mancanti**: se una categoria del mapping non ha la relativa cartella su Drive, viene **segnalata e saltata** (non crea la cartella).

**Diff Drive ↔ Locale** Confronta i PDF presenti in `<DRIVE_ID>/<slug>/raw/<categoria>/` con quelli in `output/timmy-kb-<slug>/raw/<categoria>/`:

- **Scansione**: lato Drive considera solo `application/pdf`; lato locale considera `*.pdf`.
- **Selezione e download**: scegli i file da copiare e clicca **Scarica PDF da Drive → locale**. I file vengono salvati **nella stessa categoria**. I file **già presenti** non vengono sovrascritti; per aggiornarli rimuovi/rinomina la copia locale prima di rilanciare.
- **Avanzamento**: barra/progresso su **tutti i candidati** (anche quelli già presenti); al termine mostra i **nuovi file creati**.
- **README generati**: i `README.pdf` presenti nelle cartelle potrebbero comparire nella lista; **deselezionali** se non ti servono in locale.
- **Rileva PDF in raw/**: riesegue la **sola scansione locale** per aggiornare lo stato (utile se hai copiato manualmente dei file).
- **Cancella cliente**: rimuove l’intero workspace locale e prova a eliminare le cartelle su Drive. Operazione **irreversibile** con conferma.

---

## 6) Pipeline semantica → **Semantica**

Esegui nell’ordine (ripetibile per nuovi PDF):

1. **Converti PDF → Markdown**
   - **Cosa fa:** scansiona `raw/<categoria>/**/*.pdf`, esclude file non‑PDF/illeggibili, e crea i corrispondenti `.md` in `book/<categoria>/` (rapporto 1:1).
   - **Frontmatter aggiunto:** `title`, `source_category`, `source_file`, `created_at`, `tags_raw` (estratti automatici).
   - **Idempotenza:** genera/aggiorna solo i file nuovi o modificati; non tocca gli altri.
   - **Note/Errore tipico:** PDF protetti o corrotti vengono segnalati nei log e saltati; gli altri proseguono.
2. **Arricchisci frontmatter**
   - **Cosa fa:** trasforma `tags_raw` in `tags` **canonici** usando `semantic_mapping.yaml` (areas + system\_folders), sinonimi e regole di normalizzazione.
   - **Risultato:** frontmatter dei `.md` aggiornato con `tags` puliti e coerenti (rispettando limiti/score se configurati).
   - **Quando rilanciarlo:** dopo nuove conversioni o dopo modifiche al mapping (keywords/sinonimi/aree).
3. **Genera README/SUMMARY**
   - **SUMMARY.md:** ricostruisce l’indice navigabile di `book/` in base a cartelle e file presenti.
   - **README.md:** crea/aggiorna il README radice e, ove previsto, i README di categoria usando **ambito**/**descrizione** dal mapping.
   - **Idempotenza:** sicuro da rilanciare; modifica solo ciò che è cambiato.
4. **Anteprima Docker (HonKit)** *(facoltativa)*
   - **Cosa fa:** avvia un container che serve il sito statico generato da `book/`.
   - **Quando usarla:** per QA visivo prima della pubblicazione; chiudi il container al termine.

---

## 7) Configurazione avanzata → **Settings**

**Semantica (YAML)**

- **semantic\_mapping.yaml**: rinomina aree (kebab‑case), aggiorna **ambito/descrizione/keywords**.\
  Dopo modifiche, rigenera README (Drive) e, se serve, rifai **Arricchisci**.
- **cartelle\_raw\.yaml**: riflette la struttura di **raw/** + **contrattualistica/**.\
  In scenari standard non toccarlo a mano; se cambi le aree, mantieni coerenza.

**Retriever** (opzionale)

- Parametri di ricerca interna (candidate limit, budget latenza, auto‑budget).\
  Lasciali di default salvo esigenze specifiche.

---

## 8) Diagnostics & Log

- Vedi percorsi, conteggi file, ultimi log.
- Scarica zip dei log per supporto.
- Utile se compaiono errori di Drive/AI o conversione.

---

## 9) FAQ / Problemi comuni

- **DRIVE\_ID o SERVICE\_ACCOUNT\_FILE mancanti** → configura variabili e installa \`.[drive]\`.
- **“Cartella raw non trovata/creata”** → esegui **Apri workspace** (Step 2).
- **Nessun PDF rilevato** → carica su Drive e **Scarica**, oppure copia in locale e **Rileva PDF**.
- **README non in PDF** → manca ReportLab → viene caricato **README.txt** (comunque ok).
- **Tag strani o mancanti** → rivedi mapping (aree/keywords/sinonimi), poi **Arricchisci**.

---

## 10) Best practice

- Scegli **slug** chiari e stabili (es. \`evagrin\`).
- Carica i PDF **per categoria** (coerenza → tagging migliore).
- Dopo modifiche al mapping: **Genera README (Drive)** e (se impatta i tag) **Arricchisci**.
- Itera spesso con piccoli lotti di PDF: più rapido e sicuro.

---

## 11) Checklist rapida (per sessione)

1. Avvia UI → seleziona cliente.
2. (Se onboarding): Step 1 **Inizializza** → Step 2 **Apri workspace**.
3. **Genera README in raw (Drive)** (opzionale ma consigliato).
4. Carica PDF su Drive → **Scarica** in locale (o **Rileva** se copiati a mano).
5. **Converti** → **Arricchisci** → **Genera README/SUMMARY**.
6. (Facoltativo) **Anteprima Docker** → pubblica.

---

### Glossario minimo

- **Vision‑only mapping**: mapping semantico generato dal PDF di Vision (\`areas\`, \`system\_folders\`).
- **raw/**: cartelle con i PDF sorgenti per categoria.
- **book/**: output Markdown e indici.
- **contrattualistica/**: sezione separata per documenti legali.

*Fine.*
