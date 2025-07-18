
# 📚 Documentazione Pipeline Onboarding – Timmy KB (2025, v1.2)

## 🧭 Obiettivo

Automatizzare la generazione, strutturazione semantica, anteprima e pubblicazione di una Knowledge Base partendo da PDF contenuti in una cartella Drive condivisa, per ogni nuovo cliente.  
Tutti i path e i parametri di sistema sono caricati dinamicamente da file `.env` e dalla configurazione del cliente su Drive.

---

## 🗂️ Struttura base del progetto

```
project-root/
├── config/
│   ├── raw_structure.yaml        # (opz.) Mappa semantica delle tipologie documentali
│   └── cartelle_raw.yaml         # Template struttura cartelle cliente su Drive
├── output/
│   └── timmy_kb_<slug>/          # Output Markdown, JSON, README generati
├── clienti/
│   └── timmy-kb-<slug>/          # (opz.) Config locale cliente (copia)
├── src/
│   ├── ingest/
│   │   ├── config_loader.py      # Carica e valida config.yaml cliente da Drive
│   │   ├── pdf_to_md.py          # Estrae testo/semantica da PDF locale
│   │   ├── semantic_extractor.py # Crea semantica base da MD (placeholder JSON)
│   │   ├── build_summary.py      # Genera README.md e SUMMARY.md
│   │   ├── gitbook_preview.py    # Preview locale Honkit/GitBook via Docker
│   │   ├── github_push.py        # Push su GitHub (CLI)
│   │   └── cleanup.py            # Cleanup finale output
│   └── onboarding_full.py        # Entry-point principale della pipeline
├── .env                          # Configurazione variabili ambiente
```

---

## ⚙️ Flusso della pipeline (Onboarding)

### 1. ▶️ Avvio pipeline

Lanciare semplicemente:
```bash
py src/onboarding_full.py
```
Lo slug cliente verrà richiesto via input.  
Il nome cliente sarà recuperato automaticamente dal config YAML del cliente su Drive.

### 2. 📥 Download PDF da Google Drive

La pipeline ricerca la cartella raw del cliente (<slug>/raw) su Google Drive.  
Scarica automaticamente tutti i file PDF, anche quelli presenti in eventuali sottocartelle di raw, mantenendo la struttura originale.  
I PDF vengono salvati in una directory temporanea locale.

### 3. 🧩 Caricamento Configurazione (`config_loader.py`)

Carica `config.yaml` da Drive nella cartella del cliente.  
Legge e arricchisce i parametri tramite `.env` (Drive ID, path output, repo GitHub, ecc.).  
Valida la presenza e la coerenza dei parametri (fail-fast).  
Tutti i path di input/output vengono calcolati da template presenti nel `.env` (es. `RAW_DIR_TEMPLATE`, `OUTPUT_DIR_TEMPLATE`).

### 4. 📄 Conversione PDF → Markdown (`pdf_to_md.py`)

Cerca tutti i file PDF presenti nella directory temporanea locale, ricreata dalla struttura di Drive.  
Per ogni PDF, genera un file Markdown (conversione simulata o reale, a seconda dello stato del modulo).  
I file Markdown sono salvati nella cartella output dedicata del cliente.  
**Nota:** la pipeline è pronta per l’integrazione di conversione reale (PyMuPDF, OCR, ecc.).

### 5. 🧠 Estrazione Semantica (`semantic_extractor.py`)

Per ogni Markdown prodotto, crea JSON di semantica placeholder (`README.json`, `SUMMARY.json`) utili per step successivi di AI/NLP.  
Il modulo è pronto per evoluzione futura con parsing semantico avanzato tramite spaCy/pydantic.

### 6. 📑 Generazione README & SUMMARY (`build_summary.py`)

Genera (o aggiorna) il file `SUMMARY.md` per la navigazione GitBook/Honkit, elencando tutti i Markdown presenti.  
Crea o aggiorna `README.md` personalizzato per il cliente.

### 7. 🧪 Anteprima locale via Docker (`gitbook_preview.py`)

Avvia un container Docker con Honkit per visualizzare la documentazione localmente su `http://localhost:4000`.  
Il path di output e l’immagine Docker sono parametrizzati da `.env`.  
L’utente conferma manualmente la prosecuzione al termine della preview.

### 8. 🚀 Deploy su GitHub (`github_push.py`)

Chiede conferma interattiva per il push su GitHub.  
Se confermato, crea la repository (visibilità configurabile) e carica i file generati.  
Utilizza GitHub CLI (`gh`) autenticato e configurato.  
I parametri di repo (nome, owner, path) sono caricati dinamicamente da `.env` e `config.yaml`.

### 9. 🧹 Cleanup finale (`cleanup.py`)

Chiede conferma per la cancellazione dei file di output generati.  
Svuota solo la directory di output attesa, evitando errori su altre directory.

---

## ✅ Risultati Finali

- Output Markdown e JSON per la Knowledge Base del cliente.  
- File `README.md` e `SUMMARY.md` navigabili in Honkit/GitBook.  
- Repository GitHub aggiornata e pubblicata.  
- Log dettagliato di tutte le operazioni principali.

---

## 🛠️ Requisiti tecnici

| Componente     | Requisito                                               |
|----------------|----------------------------------------------------------|
| Python         | >= 3.10                                                  |
| Librerie       | PyMuPDF, spacy, pydantic, pyyaml, slugify, google-api-python-client, docker, requests |
| Docker         | Per preview Honkit/GitBook                               |
| GitHub CLI     | `gh` autenticato                                         |
| Google Drive   | Service Account configurato (.env)                       |

---

## ⚡ Note di portabilità e sicurezza

- Tutti i parametri ambientali e i path sono centralizzati in `.env`.  
- La pipeline fallisce immediatamente in caso di parametri/config mancanti.  
- È garantita la compatibilità cross-platform (Windows/Linux) tramite path dinamici.  
- Nessun dato sensibile deve essere committato nei repository (occhio a `.env`).

---

## 🔗 Evoluzioni possibili (roadmap)

- Conversione PDF→MD reale, arricchimento semantico, pipeline CI/CD automatica, integrazione AI con Q&A/document search.  
- Logging avanzato su file rotanti.  
- Interfaccia CLI più flessibile (flag per step non interattivi).  
- Download e parsing automatico anche di altri formati (docx, immagini, etc.).

---

## 🧑‍💻 Note di sviluppo

- Tutti i moduli sono documentati tramite docstring.  
- Il sistema è progettato per essere riusabile e scalabile per più clienti.  
- La configurazione ambientale e i template sono facilmente adattabili da `.env`.
