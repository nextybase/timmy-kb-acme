
# 📦 Onboarding Pipeline Timmy-KB – v1.0

Versione: 1.0 
Data: 2025-09-04  
Owner: NeXT Dev Team

---

## 🧭 Scopo della pipeline

Questa pipeline automatizza il processo di onboarding per ogni cliente/PMI,  
creando una knowledge base AI-ready (formato markdown arricchito, tagging semantico, frontmatter esteso)  
partendo dai PDF/artefatti reali dell’organizzazione e mantenendo la piena tracciabilità per knowledge graph, audit e validazione.

---

## 🚦 Flusso operativo (step-by-step)

### 1️⃣ Pre-onboarding

- Esegui:
  py src/pre_onboarding.py
  ```
- Funzioni:
  - Generazione struttura standard su Google Drive per il cliente (cartelle tematiche)
  - Creazione file config YAML arricchito (`output/timmy-kb-<slug>/config/config.yaml`)
  - Logging dettagliato e validazione automatica
  - Se la struttura esiste già, la procedura blocca ed esce con rollback
- Lo slug cliente è in formato `timmy-kb-<slug>`, naming policy in [coding_rule.md](./coding_rule.md)
- Dopo questa fase il cliente carica i propri PDF/artefatti direttamente nelle cartelle condivise di Drive

---

### 2️⃣ Onboarding completo

- Esegui:
  py src/onboarding_full.py
  ```
- Funzioni:
  - Caricamento config e validazione repo GitHub di destinazione
  - Download ricorsivo di tutti i PDF dalla struttura cliente su Drive (cartelle tematiche mantenute)
  - Conversione automatica di tutti i PDF in markdown con:
    - **Parsing avanzato:** suddivisione in paragrafi “logici”, titoli reali, elenchi markdown, pulizia spezzature
    - **Frontmatter esteso** (titolo, categoria, origine cartella, data conversione…)
    - **Tagging semantico per paragrafo**: matching delle keyword ufficiali da YAML, output `<!-- tags: ... -->` solo per paragrafi rilevanti
  - Enrichment semantico (facoltativo): aggiunta metadati, mapping, ulteriori arricchimenti via moduli plugin
  - Generazione automatica di `README.md` e `SUMMARY.md` per GitBook/Honkit
  - Preview locale con Docker+Honkit (facoltativo)
  - Deploy/push su repo GitHub (con controllo interattivo, rollback su errori)
  - Logging strutturato, nessuna stampa superflua

---

### 3️⃣ Enrichment semantico avanzato (standalone/fase plugin)

- Esegui:
  py src/semantic/semantic_extractor.py
  ```
- Funzioni:
  - Arricchisce i markdown prodotti con metadati e tagging aggiuntivi (pronto per pipeline KG/AI)
  - Possibilità di rigenerare README e SUMMARY
  - Logging e rollback in caso di errori

---

### 4️⃣ Testing e convenzione

- Tutti i test sono in `/tests/`
- Output dei test in `/output/timmy-kb-dummy/`
- Pulizia obbligatoria a fine test (prompt CLI per cancellazione)
- Dettaglio policy e naming: vedi [coding_rule.md](./coding_rule.md)

---

## 📚 Configurazione e policy

- **Configurazione centralizzata**: tutte le variabili principali sono in `.env` e `config/`
- **Lista tag ufficiali**: file YAML per categorie in `config/timmy_tags.yaml`
- **Mapping semantico cartelle**: file YAML in `config/`
- **Policy di naming, logging, testing**: tutte in [coding_rule.md](./coding_rule.md)

---

## 🧩 Tecnologie e dipendenze

- Python >= 3.10
- PyMuPDF, spacy, pyyaml, google-api-python-client, docker, requests, gitpython, PyGithub, python-slugify, pydantic
- Docker (per preview GitBook)
- GitHub CLI configurato
- Service Account JSON Google

---

## 🗂️ Changelog (sintesi v1.3)

- Pipeline parsing/conversione PDF→Markdown completamente rinnovata, frontmatter esteso
- Tagging semantico integrato e AI-ready, policy ufficiale YAML
- Logging strutturato, nessun print nei moduli di produzione
- Testing e convenzione file formalizzati, policy raccolte in `coding_rule.md`
- Tutto pronto per evoluzione Knowledge Graph/AI e arricchimento plugin

---

> Per ogni evoluzione strutturale, aggiornare [coding_rule.md](./coding_rule.md) e seguire le convenzioni riportate.
