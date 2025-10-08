# Onboarding UI – Guida (Beta 0)

Questa guida descrive l’interfaccia Streamlit dell’onboarding **Timmy‑KB** così come implementata in **Beta 0**.

- **Router nativo**: `st.navigation` + `st.Page` (niente `pages/` legacy, niente router a tab).
- **Deep‑linking**: `st.query_params` (es. `?slug=acme&tab=semantics`).
- **Streamlit**: **>= 1.50** (solo API stabili: nessun `experimental_*`, nessun `use_container_width`).
- **UI**: pulsanti con `width="stretch"`; HTML solo tramite `st.html(...)`.

> Avvio rapido:
> ```bash
> streamlit run onboarding_ui.py
> ```

---

## Navigazione & struttura

La navigazione è **in alto** (top) ed è suddivisa in gruppi:

- **Onboarding**
  - **Home** (`src/ui/pages/home.py`)
  - **Gestisci cliente** (`src/ui/pages/manage.py`)
  - **Semantica** (`src/ui/pages/semantics.py`)
- **Tools**
  - **Docker Preview** (`src/ui/pages/preview.py`)
  - **Cleanup** (`src/ui/pages/cleanup.py`)
  - *(interno, per diagnostica/test)* **Diagnostics** (`src/ui/pages/diagnostics.py`)

> L’entrypoint `onboarding_ui.py` configura la pagina, idrata i **query params** e registra le pagine nel router.

### Query params supportati
- `slug`: seleziona il cliente attivo (es. `?slug=acme`).
- `tab`: percorso pagina (es. `?tab=semantics`). Viene impostato a `home` se mancante.

---

## Header & Sidebar

- L’**header** mostra il titolo *“Timmy‑KB • Onboarding”* e, se presente, lo **slug** corrente.
- La **sidebar** espone **Azioni rapide**:
  - **Aggiorna Drive**: invalida la cache dell’albero Drive.
  - **Dummy KB**: genera un dataset locale di prova per lo slug.
  - **Esci**: shutdown dell’app.
- Nella sidebar è presente anche il box **Ricerca (retriever)** con i parametri:
  - *Candidate limit*, *Budget latenza (ms)*, *Auto per budget* (persistono in config cliente).

> Tutte le azioni mostrano spinner/toast e log strutturati; nessuna API `experimental_*` è usata.

---

## Pagine

### Home
Pagina informativa con link rapidi e indicazioni di flusso. Supporta deep‑linking allo **slug** via querystring.

### Gestisci cliente
- Campo **Slug cliente** con pulsante **Apri workspace** → imposta `slug` nei query params e fa `st.rerun()`.
- Se uno **slug** è attivo, la pagina ospita tre blocchi affiancati:
  1) **Albero Drive** – gerarchia da `DRIVE_ID/<slug>/` (focus su `raw/`).
  2) **Diff Drive vs locale** – confronta `raw/` remoto con `output/timmy-kb-<slug>/raw/`; include **Scarica da Drive in raw/** con `st.status`.
  3) **Editor tag** – authoring e sync di `semantic/tags_reviewed.yaml`; **Estrai Tags** genera `tags_raw.csv` e aggiorna lo stub.

> Le funzioni Drive hanno guardie: se mancano gli extra (`google-api-python-client`) la UI mostra un messaggio con le istruzioni di installazione.

### Semantica
Flusso a pulsanti:
- **Converti PDF in Markdown** → `semantic.api.convert_markdown(...)` (solo PDF **sicuri** in `raw/`).
- **Arricchisci frontmatter** → `semantic.api.enrich_frontmatter(...)` usando il **vocabolario consolidato**.
- **Genera README/SUMMARY** → idempotente, valida `book/`.
- **Anteprima Docker (HonKit)** → delega alla pagina *Docker Preview*.

**Gating**: la pagina è utilizzabile solo **se lo stato del cliente risulta tra 'pronto', 'arricchito' o 'finito'**.


### Docker Preview (Tools)
Avvia/arresta la preview HonKit in container Docker. Se Docker non è disponibile, la pagina mostra un messaggio esplicito e salta la preview.

### Cleanup (Tools)
Azioni di pulizia locale per workspace e artefatti temporanei.

### Diagnostics (interno)
Pagina ausiliaria per i test/smoke. Mostra:
- `base_dir` del cliente corrente, conteggi `raw/`, `book/`, `semantic/`.
- **Tail** (≈4 KB) dell’ultimo file in `logs/` con **download ZIP** di tutti i log.

---

## Regole di qualità (Definition of Done – UI Beta 0)

- Solo `st.navigation` + `st.Page` (nessun mix con la cartella `pages/` legacy o router a tab).
- Stato/URL: `st.query_params` per `slug` e `tab`; deep‑linking funzionante.
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

> `tags.db` è la SSoT a runtime; lo YAML resta per authoring/validazione.

---

## FAQ
- **Come avvio l’interfaccia?** `streamlit run onboarding_ui.py`.
- **Perché non vedo la pagina “Semantica”?** Non risultano PDF in `raw/`. Scaricali da Drive o copia file locali (no symlink).
- **Posso generare i tag senza Drive?** Sì: usa `--source=local` o popola `raw/` manualmente.
- **È rimasta retro‑compatibilità con i vecchi tab?** No: il router legacy e i relativi helper sono stati rimossi in Beta 0.

---

Documento mantenuto in ASCII per evitare problemi di encoding; cSpell‑friendly.
