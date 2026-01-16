# Arricchimento semantico - Flusso completo (UI / CLI) - Beta 1.0

Timmy-KB è un ambiente di **governo e orchestrazione**.
Questa sezione descrive il **funzionamento tecnico dello strumento di arricchimento semantico**,
che opera entro l'envelope epistemico definito dal sistema, supporta HiTL
e **non prende decisioni autonome di avanzamento o stato**.

Le decisioni di stato sono sempre demandate a:
- Engineering Gatekeeper / OCP-plane,
- tramite Decision Record append-only.

---

## 1) Innesco dalla UI

- Pagine coinvolte: `ui.pages.manage`
- Azione: **Estrai tag / Avvia arricchimento semantico**
- Handler: `ui.services.tags_adapter.run_tags_update(slug)`
- Effetti immediati:
  - risoluzione del contesto cliente (`base_dir`, `raw_dir`, `semantic_dir`);
  - verifica path-safety;
  - avvio della run tecnica di estrazione.

**Nota normativa**
- L'innesco UI **non modifica alcuno stato workspace**.
- Produce solo evidenze e log per i gate successivi.

---

## 2) Backend di tagging (configurazione)

- Backend selezionato tramite:
  - `semantic_defaults.nlp_backend` in `config/config.yaml`, oppure
  - `TAGS_NLP_BACKEND` da env.
- Valori ammessi:
  - `spacy`
  - `heuristic`

### Policy Beta 1.0
- L'uso di `heuristic` è **una scelta esplicita**, non un fallback automatico.
- Se `nlp_backend=spacy` e SpaCy **non è disponibile o fallisce**:
  - la run tecnica **deve fallire**,
  - viene prodotto evento strutturato,
  - il Gatekeeper decide se BLOCK o FAIL.

---

## 3) Pipeline di estrazione (produzione evidenze)

### 3.1 Euristica (sempre disponibile come modalità esplicita)

- Modulo: `semantic.auto_tagger`
- Metodo: `_extract_semantic_candidates_heuristic`
- Sorgenti:
  - segmenti di cartella sotto `raw/`,
  - nome file.
- Scoring:
  - path (peso 1.0),
  - filename (peso 0.6),
  - stoplist da config,
  - `top_k`.

**Output per file**
- `tags`
- `score`
- `sources` (`path`, `filename`)

---

### 3.2 SpaCy (solo se configurato e disponibile)

- Modulo: `semantic.spacy_extractor`
- Lettura PDF: PyPDF2 (lazy import)
- NLP:
  - noun chunks,
  - entità.
- Mapping aree:
  - `semantic_mapping.yaml`
- Scoring:
  - accumulo pesi per area/keyword,
  - ordinamento,
  - `top_k`.
- Metadata:
  - `entities`
  - `keyphrases`

**Policy Beta 1.0**
- Se SpaCy fallisce:
  - evento `semantic.spacy.unavailable` o `semantic.spacy.failed`,
  - run tecnica fallita,
  - nessuna prosecuzione automatica.

---

### 3.3 Merge euristica + SpaCy

- Deduplica tag.
- Somma pesi.
- Merge `entities` / `keyphrases`.
- Arricchimento sorgenti (`sources.spacy`).
- Normalizzazione tramite `semantic.normalizer`.

Il merge **non implica validazione** né avanzamento di stato.

---

## 4) Scrittura dei risultati (evidenze)

- CSV: `semantic/tags_raw.csv`
  - colonne: `relative_path`, `suggested_tags`, `entities`, `keyphrases`, `score`, `sources`
- README tagging: `semantic/README_TAGGING.md`
- Persistenza SpaCy:
  - DB `semantic/tags.db`
  - tabella `doc_entities`
  - `status = suggested`

Questi artefatti sono **input per il Gatekeeper**, non output decisionali.

---

## 5) Revisione HiTL e consolidamento

- Modal "Revisione keyword (tags_raw.csv)":
  - editing manuale,
  - salvataggio.
- Azione **Abilita**:
  - genera `tags_reviewed.yaml`,
  - sincronizza `tags.db`.

**Nota normativa**
- Questa fase **non aggiorna lo stato workspace**.
- Produce solo evidenze per:
  - Evidence Gate,
  - Skeptic Gate,
  - eventuale QA Gate.

---

## 6) Arricchimento frontmatter

- Servizio: `semantic.frontmatter_service.enrich_frontmatter`
- Input:
  - `tags_reviewed.yaml`,
  - `tags.db`.
- Output:
  - frontmatter con `entities` e `relations_hint`
    (basato su Vision mapping).

- Produzione documenti:
  - `SUMMARY.md`
  - `README.md`
  - file in `book/`

Anche questa fase **non attesta stato**.

---

## 7) Decisione di avanzamento (fuori scope del tool)

L'avanzamento a stati come `FRONTMATTER_ENRICH`, `VISUALIZATION_REFRESH`, `PREVIEW_READY`
avviene **solo** se:
- i gate richiesti emettono Decision Record PASS,
- secondo quanto definito in:
  - `instructions/05_pipeline_workspace_state_machine.md`
  - `instructions/06_promptchain_workspace_mapping.md`.

---

## 8) Configurazioni rilevanti

- `config/config.yaml` → `semantic_defaults`
- `semantic/semantic_mapping.yaml`
- Env override:
  - `TAGS_NLP_BACKEND`
  - `SPACY_MODEL`

Ogni modifica di configurazione:
- è auditabile,
- influisce sulla run successiva,
- non altera retroattivamente stati o decisioni.

---

## 9) Summary operativo

1. UI avvia run tecnica.
2. Produzione evidenze (euristica / SpaCy).
3. Scrittura artefatti (`tags_raw.csv`, DB, README).
4. Revisione HiTL.
5. Arricchimento frontmatter.
6. **Gatekeeper decide** (PASS / BLOCK / FAIL).
7. Eventuale retry come **nuova run**.

---

## 10) doc_entities e hook disponibili

- DB `semantic/tags.db`:
  - `doc_entities` con status `suggested`, `approved`, `rejected`.
- Modulo `semantic.entities_review`:
  - helper riutilizzabili per UI / script / CLI.
- Le funzioni:
  - sono import-safe,
  - non producono side effect a import-time,
  - non aggiornano stati di pipeline.
