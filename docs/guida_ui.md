# Guida Onboarding UI

Questa guida descrive l’interfaccia Streamlit dell’onboarding **Timmy‑KB** così come implementata attualmente (Beta 0), allineata al codice nel repository.

- **Router nativo**: `st.navigation` + `st.Page` (nessuna cartella `pages/` legacy, nessun router a tab).
- **Deep‑linking**: `st.query_params` (es. `?slug=acme&tab=semantics`).
- **Versione Streamlit**: **>= 1.50** (solo API stabili: nessun `experimental_*`, nessun `use_container_width`).
- **UI**: pulsanti con `width="stretch"`; HTML solo tramite `st.html(...)`.
- **Tema**: gestione **nativa di Streamlit**. Nessun toggle custom; il CSS brand viene iniettato automaticamente.

> Avvio rapido:
>
> ```bash
> streamlit run onboarding_ui.py
> ```

---

## Navigazione & struttura

La navigazione è **in alto** (top) ed è suddivisa in gruppi:

- **Onboarding**
  - **Home** (`src/ui/pages/home.py`)
  - **Nuovo cliente** (`src/ui/pages/new_client.py`)
  - **Gestisci cliente** (`src/ui/pages/manage.py`)
  - **Semantica** (`src/ui/pages/semantics.py`)
- **Tools**
  - **Settings** (`src/ui/pages/settings.py`)
  - **Docker Preview** (`src/ui/pages/preview.py`)
  - **Cleanup** (`src/ui/pages/cleanup.py`)
  - *(interno, per diagnostica/test)* **Diagnostics** (`src/ui/pages/diagnostics.py`)

> L’entrypoint `onboarding_ui.py` configura la pagina, idrata i **query params** e registra le pagine nel router.

### Query params supportati

- `slug`: seleziona il cliente attivo (es. `?slug=acme`).
- `tab`: percorso pagina (es. `?tab=semantics`). Viene impostato a `home` se mancante.

---

## Header & Sidebar

- L’**header** mostra il titolo e, se presente, lo **slug** corrente. Il CSS brand viene applicato automaticamente.
- La **sidebar** espone **Azioni rapide**:
  - **Guida UI**: link alla documentazione del progetto.
  - **Dummy KB**: pulsante informativo per dataset di prova (flag UI; l’esecuzione della generazione è esterna/da CLI).
  - **Esci**: arresta l’app in modo controllato.

> Nota: il pannello **Retriever** *non* è più in sidebar. È stato spostato nella pagina **Settings**.

---

## Pagine

### Home

Pagina informativa con link rapidi. Il bottone/link **Nuovo cliente** porta alla pagina omonima (router nativo).

### Nuovo cliente

Wizard in due step:

1. **Inizializza Workspace**
   - Inserisci **slug** (obbligatorio) e (opzionale) **nome** cliente.
   - Carica **VisionStatement.pdf**.
   - La UI crea la struttura locale, salva `config.yaml` e il PDF ed **esegue Vision** generando i due YAML richiesti (`semantic_mapping.yaml`, `cartelle_raw.yaml`).
2. **Apri workspace**
   - Crea la struttura su **Drive** (se configurata), finalizza le cartelle locali e aggiorna il **registro clienti (SSoT)** con stato `pronto`.
   - Non riesegue Vision.

> Il wizard aggiorna anche il **registro clienti (SSoT)** con lo stato **italiano** `pronto`.

### Gestisci cliente

Comportamento condizionato allo **slug** attivo:

- **Se lo slug non è impostato**: mostra il box *Gestione cliente* con input *Slug cliente* e i pulsanti **Apri workspace** e **Cancella cliente** (quest’ultimo richiede conferma esplicita e invoca la pulizia locale/DB/Drive quando disponibile).
- **Se lo slug è impostato**: mostra due colonne operative:
  1. **Albero Drive** – gerarchia da `DRIVE_ID/<slug>/` (focus su `raw/`). Se gli extra Drive non sono presenti, appare un messaggio con le istruzioni.
  2. **Diff Drive vs Locale** – confronta `raw/` remoto con `output/timmy-kb-<slug>/raw/` e supporta lo scaricamento dei file da Drive (quando abilitato).

> Sono state rimosse le vecchie intestazioni “Drive: Albero…” e “Diff: Drive vs Locale” per un look più pulito.

### Semantica

Flusso a pulsanti:

- **Converti PDF in Markdown** → `semantic.api.convert_markdown(...)` (solo PDF **sicuri** in `raw/`).
- **Arricchisci frontmatter** → `semantic.api.enrich_frontmatter(...)` usando il **vocabolario consolidato**.
- **Genera README/SUMMARY** → genera `README.md` e `SUMMARY.md` in modo idempotente.
- **Anteprima Docker (HonKit)** → delega alla pagina *Docker Preview*.

**Gating**: la pagina è utilizzabile solo \*\*se lo stato del cliente è uno tra ``, ``, \*\*`` e `raw/` contiene PDF. Lo stato è letto dal registro SSoT.

### Settings (Tools)

- **Retriever**:
  - *Candidate limit*, *Budget latenza (ms)*, *Auto per budget*. I valori sono persistenti e impattano la ricerca.
- **Semantica (YAML)**: editor dedicati per:
  - `semantic/semantic_mapping.yaml`
  - `semantic/cartelle_raw.yaml`

> Gli editor YAML sono stati spostati qui da *Gestisci cliente* per mantenere pulita la pagina operativa.

### Docker Preview (Tools)

Pagina dedicata all’anteprima HonKit via Docker. Se Docker non è disponibile, la pagina lo segnala e salta l’azione.

### Cleanup (Tools)

Azioni di pulizia locale per workspace e artefatti temporanei. La cancellazione per‑cliente è esposta anche da *Gestisci cliente* (pulsante **Cancella cliente** con conferma).

### Diagnostics (interno)

Pagina ausiliaria per i test/smoke. Mostra:

- `base_dir` del cliente corrente, conteggi `raw/`, `book/`, `semantic/`.
- **Tail** (≈4 KB) dell’ultimo file in `logs/` con **download ZIP** di tutti i log.

---

## Regole di qualità (Definition of Done – UI Beta 0)

- Solo `st.navigation` + `st.Page` (nessun mix con la cartella `pages/` legacy o router a tab).
- Stato/URL: `st.query_params` per `slug` e `tab`; deep‑linking funzionante e idempotente.
- Zero `experimental_*` e zero `use_container_width`.
- Caching solo con `@st.cache_data` / `@st.cache_resource`.
- HTML sanificato con `st.html(...)`.
- Nessun riferimento a `src/ui/app.py` o `src/ui/tabs/*`.

---

## Struttura workspace cliente

```
output/
  timmy-kb-<slug>/
    raw/
    book/
    semantic/
      semantic_mapping.yaml
      cartelle_raw.yaml
      tags_reviewed.yaml
      tags_raw.csv
      tags.db
    config/
      config.yaml
      VisionStatement.pdf
    logs/
```

> `tags.db` è la **SSoT a runtime**; gli YAML restano per authoring/validazione.

---

## Stato cliente (terminologia)

Le stringhe di **stato cliente** persistite nel registro sono **in italiano** e usate per il gating della *Semantica*:

- `pronto` → workspace inizializzato correttamente
- `arricchito` → frontmatter arricchito
- `finito` → pipeline semantica completata

> Le **fasi UI del wizard** (es. `init`, `ready_to_open`, `provisioned`) sono interne alla pagina *Nuovo cliente* e non vengono persistite nel registro.

---

## FAQ

- **Come avvio l’interfaccia?** `streamlit run onboarding_ui.py`.
- **Perché non vedo la pagina “Semantica”?** O lo stato non è tra `pronto|arricchito|finito`, oppure non ci sono PDF in `raw/`. Scaricali da Drive o copia file locali (no symlink).
- **Posso lavorare senza Drive?** Sì: popola `raw/` manualmente e lavora in locale.
- **Retro‑compatibilità con router/“tab” legacy?** No: il router legacy e i relativi helper sono stati rimossi in Beta 0.

---

Documento mantenuto in ASCII per evitare problemi di encoding; cSpell‑friendly.
